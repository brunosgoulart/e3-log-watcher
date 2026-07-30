from __future__ import annotations

from datetime import timedelta
from numbers import Real

from app.config.models import AppConfig
from app.data_quality.service import classify_collection_timestamp
from app.domain.models import (
    GroupObservation,
    GroupRuntimeState,
    RedundancyState,
    SampleClassification,
    StateDecision,
)


class RedundancyStateMachine:
    """Evidence-based state transitions; it never guesses a physical active server."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def update(
        self,
        previous: GroupRuntimeState | None,
        observation: GroupObservation | None,
        acquisition_success: bool,
    ) -> StateDecision:
        if observation is None:
            raise ValueError("An observation timestamp is required to update group state")
        runtime = previous or GroupRuntimeState(group_id=observation.group_id, state_since=observation.observed_at)
        if not acquisition_success:
            return self._decision(
                runtime,
                observation,
                RedundancyState.ACQUISITION_FAILURE,
                SampleClassification.MISSING,
                ["PI acquisition did not complete successfully"],
                0.95,
            )
        classification = classify_collection_timestamp(
            runtime.previous_collection_timestamp,
            observation.collection_timestamp,
            observation.observed_at,
            self._config.acquisition,
        )
        if observation.quality_ratio < self._config.quality.minimum_group_quality_ratio:
            return self._decision(
                runtime,
                observation,
                RedundancyState.UNKNOWN,
                classification,
                [f"group quality ratio {observation.quality_ratio:.2f} is below configured minimum"],
                0.3,
            )
        status = observation.metrics.get("E3Server.Status")
        age = (
            (observation.observed_at - observation.collection_timestamp).total_seconds()
            if observation.collection_timestamp
            else None
        )
        if (
            isinstance(status, str)
            and status in self._config.redundancy.unavailable_status_values
            and age is not None
            and age >= self._config.acquisition.unavailable_after_seconds
        ):
            return self._decision(
                runtime,
                observation,
                RedundancyState.APPLICATION_UNAVAILABLE,
                classification,
                ["configured unavailable E3Server.Status", "collection timestamp exceeded unavailable timeout"],
                0.8,
            )
        if classification == SampleClassification.STALE:
            return self._decision(
                runtime,
                observation,
                RedundancyState.STALE,
                classification,
                ["CollectionTimeStamp did not advance within stale tolerance"],
                0.85,
            )
        if classification in {SampleClassification.MISSING, SampleClassification.OUT_OF_ORDER}:
            return self._decision(
                runtime,
                observation,
                RedundancyState.UNKNOWN,
                classification,
                [f"collection sample classified as {classification.value}"],
                0.3,
            )
        evidence = self._switchover_evidence(runtime, observation, classification)
        if len(evidence) >= self._config.redundancy.minimum_switchover_evidence:
            return self._decision(
                runtime,
                observation,
                RedundancyState.SWITCHOVER_SUSPECTED,
                classification,
                evidence,
                min(0.9, 0.45 + 0.12 * len(evidence)),
                start_new_session=True,
                session_reason="possible_switchover",
            )
        if runtime.state == RedundancyState.SWITCHOVER_SUSPECTED:
            updated = self._decision(
                runtime,
                observation,
                RedundancyState.POST_SWITCHOVER_STABILIZING,
                classification,
                ["possible switchover requires stabilization before normal analysis"],
                0.6,
            )
            updated.runtime.stabilizing_until = observation.observed_at + timedelta(
                seconds=self._config.acquisition.stabilization_seconds
            )
            updated.runtime.stable_samples = 1
            return updated
        if runtime.state == RedundancyState.POST_SWITCHOVER_STABILIZING:
            stable_samples = runtime.stable_samples + (1 if classification in {SampleClassification.NEW, SampleClassification.DELAYED} else 0)
            until = runtime.stabilizing_until or observation.observed_at
            if observation.observed_at >= until and stable_samples >= self._config.acquisition.minimum_valid_samples:
                decision = self._decision(
                    runtime,
                    observation,
                    RedundancyState.ACTIVE_COLLECTING,
                    classification,
                    ["stabilization interval and minimum valid samples completed"],
                    0.75,
                )
            else:
                decision = self._decision(
                    runtime,
                    observation,
                    RedundancyState.POST_SWITCHOVER_STABILIZING,
                    classification,
                    ["stabilization interval is still active"],
                    0.55,
                )
            decision.runtime.stabilizing_until = until
            decision.runtime.stable_samples = stable_samples
            return decision
        if classification == SampleClassification.REPEATED:
            target = runtime.state if runtime.state == RedundancyState.ACTIVE_COLLECTING else RedundancyState.INITIALIZING
            return self._decision(runtime, observation, target, classification, ["CollectionTimeStamp repeated but is not stale"], 0.55)
        valid_samples = runtime.valid_samples + 1
        target = (
            RedundancyState.ACTIVE_COLLECTING
            if valid_samples >= self._config.acquisition.minimum_valid_samples
            else RedundancyState.INITIALIZING
        )
        decision = self._decision(
            runtime,
            observation,
            target,
            classification,
            ["CollectionTimeStamp advanced and group quality is acceptable"],
            0.75 if target == RedundancyState.ACTIVE_COLLECTING else 0.5,
            start_new_session=runtime.session_id is None,
            session_reason="initial_valid_collection" if runtime.session_id is None else None,
        )
        decision.runtime.valid_samples = valid_samples
        return decision

    def _switchover_evidence(
        self,
        runtime: GroupRuntimeState,
        observation: GroupObservation,
        classification: SampleClassification,
    ) -> list[str]:
        evidence: list[str] = []
        if runtime.state == RedundancyState.STALE and classification in {SampleClassification.NEW, SampleClassification.DELAYED}:
            evidence.append("collection resumed after stale state")
        old_uptime = runtime.previous_metrics.get("E3Run.UpTimeMinutes")
        new_uptime = observation.metrics.get("E3Run.UpTimeMinutes")
        if self._decreased(old_uptime, new_uptime):
            evidence.append("E3Run.UpTimeMinutes decreased")
        if self._changed(runtime.previous_metrics.get("FileRead"), observation.metrics.get("FileRead")):
            evidence.append("FileRead changed")
        if self._changed(runtime.previous_metrics.get("E3Server.Status"), observation.metrics.get("E3Server.Status")):
            evidence.append("E3Server.Status changed")
        for suffix in self._config.redundancy.reset_sensitive_metric_suffixes:
            if self._decreased(runtime.previous_metrics.get(suffix), observation.metrics.get(suffix)):
                evidence.append(f"{suffix} decreased")
        return evidence

    @staticmethod
    def _decreased(previous: object, current: object) -> bool:
        return (
            isinstance(previous, Real)
            and not isinstance(previous, bool)
            and isinstance(current, Real)
            and not isinstance(current, bool)
            and current < previous
        )

    @staticmethod
    def _changed(previous: object, current: object) -> bool:
        return previous is not None and current is not None and previous != current

    def _decision(
        self,
        runtime: GroupRuntimeState,
        observation: GroupObservation,
        target: RedundancyState,
        classification: SampleClassification,
        evidence: list[str],
        confidence: float,
        start_new_session: bool = False,
        session_reason: str | None = None,
    ) -> StateDecision:
        updated = runtime.model_copy(deep=True)
        if target != runtime.state:
            updated.state = target
            updated.state_since = observation.observed_at
        if classification not in {SampleClassification.MISSING, SampleClassification.OUT_OF_ORDER}:
            if (
                observation.collection_timestamp is not None
                and (
                    updated.previous_collection_timestamp is None
                    or observation.collection_timestamp >= updated.previous_collection_timestamp
                )
            ):
                updated.previous_collection_timestamp = observation.collection_timestamp
            updated.previous_metrics = observation.metrics
        updated.last_quality_ratio = observation.quality_ratio
        updated.last_missing_metrics = observation.missing_metrics
        return StateDecision(
            runtime=updated,
            evidence=evidence,
            confidence=confidence,
            classification=classification,
            start_new_session=start_new_session,
            session_reason=session_reason,
        )
