from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from threading import Event
from typing import Sequence
from uuid import uuid4

from app.acquisition.interfaces import PiClient, PiClientError
from app.alarms.service import PhaseOneAlarmService
from app.config.models import AppConfig
from app.domain.models import GroupObservation, GroupRuntimeState
from app.normalization.normalizer import EventNormalizer
from app.redundancy.state_machine import RedundancyStateMachine
from app.sessions.service import SessionService
from app.storage.sqlite import SqliteRepository


class MonitoringService:
    """Coordinates adapters without allowing transport failures to become performance alarms."""

    def __init__(self, config: AppConfig, client: PiClient, repository: SqliteRepository, logger: logging.Logger) -> None:
        self._config = config
        self._client = client
        self._repository = repository
        self._logger = logger
        self._normalizer = EventNormalizer(config)
        self._state_machine = RedundancyStateMachine(config)
        self._sessions = SessionService()
        self._alarms = PhaseOneAlarmService()
        self._runtime: dict[str, GroupRuntimeState] = repository.latest_runtime_states()

    def run_once(self) -> int:
        tags = self._config.authorized_tags
        batch = None
        acquisition_error = None
        for attempt in range(self._config.pi_system.retry_attempts + 1):
            try:
                batch = self._client.fetch_current(tags)
                break
            except PiClientError:
                acquisition_error = "PI client query failed"
                if attempt < self._config.pi_system.retry_attempts:
                    time.sleep(self._config.pi_system.retry_delay_seconds)
        if batch is None:
            now = datetime.now(timezone.utc)
            acquisition_id = str(uuid4())
            self._repository.record_acquisition(
                acquisition_id, now, False, "pi_client", "current", tags, acquisition_error
            )
            self._logger.error("PI acquisition failed", extra={"event": "acquisition_failed", "acquisition_id": acquisition_id})
            for group in self._config.server_groups:
                observation = self._failure_observation(group.group_id, now)
                decision = self._state_machine.update(self._runtime.get(group.group_id), observation, False)
                self._repository.record_state(decision, now)
                self._alarms.synchronize(self._repository, decision, observation)
                self._runtime[group.group_id] = decision.runtime
            return 0
        self._repository.record_acquisition(
            batch.acquisition_id,
            batch.acquired_at,
            True,
            batch.source,
            batch.query_mode,
            tags,
        )
        if self._config.acquisition.store_raw_values:
            self._repository.store_raw_events(batch)
        normalized = self._normalizer.normalize_batch(batch)
        self._repository.store_normalized_events(normalized)
        for observation in self._normalizer.build_observations(normalized):
            decision = self._state_machine.update(self._runtime.get(observation.group_id), observation, True)
            decision = self._sessions.apply(self._repository, decision, observation)
            self._repository.record_state(decision, observation.observed_at)
            self._alarms.synchronize(self._repository, decision, observation)
            self._runtime[observation.group_id] = decision.runtime
            self._logger.info(
                "Group state updated",
                extra={"event": "state_updated", "group_id": observation.group_id, "state": decision.runtime.state.value},
            )
        self._logger.info(
            "PI acquisition completed",
            extra={"event": "acquisition_completed", "acquisition_id": batch.acquisition_id, "count": len(batch.events)},
        )
        return len(normalized)

    def import_historical(self, start: datetime, end: datetime) -> int:
        """Store historical events in arrival order; no future data feeds online state."""
        if end < start:
            raise ValueError("Historical end must not precede start")
        cursor = start
        batch_size = timedelta(hours=self._config.acquisition.historical_batch_hours)
        overlap = timedelta(seconds=self._config.acquisition.overlap_seconds)
        seen_events: set[str] = set()
        imported_count = 0
        while cursor <= end:
            batch_end = min(end, cursor + batch_size)
            batch = self._client.fetch_recorded(self._config.authorized_tags, cursor, batch_end)
            unique_events = []
            for event in batch.events:
                fingerprint = event.model_dump_json()
                if fingerprint not in seen_events:
                    seen_events.add(fingerprint)
                    unique_events.append(event)
            batch = batch.model_copy(update={"events": unique_events})
            self._repository.record_acquisition(
                batch.acquisition_id,
                batch.acquired_at,
                True,
                batch.source,
                batch.query_mode,
                self._config.authorized_tags,
            )
            if self._config.acquisition.store_raw_values:
                self._repository.store_raw_events(batch)
            normalized = self._normalizer.normalize_batch(batch)
            self._repository.store_normalized_events(normalized)
            imported_count += len(normalized)
            if batch_end == end:
                break
            next_cursor = batch_end - overlap
            cursor = next_cursor if next_cursor > cursor else batch_end
        self._logger.info(
            "Historical import completed",
            extra={"event": "historical_import_completed", "count": imported_count},
        )
        return imported_count

    def _failure_observation(self, group_id: str, now: datetime) -> GroupObservation:
        return GroupObservation(
            group_id=group_id,
            observed_at=now,
            collection_timestamp=None,
            metrics={},
            metric_validity={},
            quality_ratio=0,
            missing_metrics=list(self._config.metric_catalog),
        )


class ContinuousAcquisitionRunner:
    """Simple blocking runner intended for a worker thread or Windows service wrapper."""

    def __init__(self, service: MonitoringService, interval_seconds: int) -> None:
        self._service = service
        self._interval_seconds = interval_seconds

    def run(self, stop_event: Event) -> None:
        while not stop_event.is_set():
            self._service.run_once()
            stop_event.wait(self._interval_seconds)
