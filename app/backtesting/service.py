from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.config.models import BacktestingConfig
from app.detection.service import PhaseTwoAnalysisService
from app.domain.models import GroupObservation, RedundancyState


@dataclass(frozen=True)
class BacktestSample:
    group_id: str
    session_id: str
    state: RedundancyState
    observation: GroupObservation


@dataclass(frozen=True)
class BacktestRun:
    run_id: str
    started_at: datetime
    ended_at: datetime
    summary: dict
    events: list[dict]


class BacktestService:
    def __init__(self, config: BacktestingConfig, analysis: PhaseTwoAnalysisService) -> None:
        self._config = config
        self._analysis = analysis

    def run(self, samples: list[BacktestSample]) -> BacktestRun:
        ordered = sorted(samples, key=lambda sample: sample.observation.observed_at)
        if not ordered:
            raise ValueError("Backtest requires at least one chronological sample")
        history: dict[tuple[str, str, str], list[tuple[datetime, float]]] = {}
        events: list[dict] = []
        rule_counts: Counter[str] = Counter()
        eligible_samples = 0
        for sample in ordered:
            is_eligible = sample.state == RedundancyState.ACTIVE_COLLECTING or (
                self._config.include_stabilizing and sample.state == RedundancyState.POST_SWITCHOVER_STABILIZING
            )
            key_history = {
                suffix: values
                for (group_id, session_id, suffix), values in history.items()
                if group_id == sample.group_id and session_id == sample.session_id
            }
            if is_eligible:
                eligible_samples += 1
                _, result, _ = self._analysis.evaluate(sample.observation, sample.session_id, key_history)
                if result.triggered_rules:
                    events.append(
                        {
                            "group_id": sample.group_id,
                            "occurred_at": sample.observation.observed_at,
                            "session_id": sample.session_id,
                            "risk_index": result.risk_index,
                            "confidence": result.confidence,
                            "triggered_rules": result.triggered_rules,
                        }
                    )
                    rule_counts.update(result.triggered_rules)
            # Append only after evaluating the current time: no future leakage.
            for suffix, value in sample.observation.metrics.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    history.setdefault((sample.group_id, sample.session_id, suffix), []).append(
                        (sample.observation.observed_at, float(value))
                    )
        summary = {
            "samples": len(ordered),
            "eligible_samples": eligible_samples,
            "alarms": len(events),
            "alarms_by_rule": dict(rule_counts),
            "alarms_by_group": dict(Counter(event["group_id"] for event in events)),
            "time_in_states": dict(Counter(sample.state.value for sample in ordered)),
            "limitations": ["confirmed events, false positives and false negatives require operational labels"],
        }
        return BacktestRun(str(uuid4()), ordered[0].observation.observed_at, ordered[-1].observation.observed_at, summary, events)
