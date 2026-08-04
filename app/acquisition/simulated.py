from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence
from zoneinfo import ZoneInfo

from app.acquisition.interfaces import PiClient
from app.config.models import AppConfig
from app.domain.models import AcquisitionBatch, PiEvent
from app.validation.tags import TagAuthorizer


class SimulatedPiClient(PiClient):
    """Deterministic synthetic PI client. It is never a source of production data."""

    def __init__(
        self,
        config: AppConfig,
        events_by_tag: dict[str, list[PiEvent]] | None = None,
        clock: datetime | None = None,
    ) -> None:
        self._config = config
        self._authorizer = TagAuthorizer(config)
        self._events_by_tag = events_by_tag or {}
        self._clock = clock or datetime.now(timezone.utc).replace(microsecond=0)
        self._sequence = 0

    def advance(self, seconds: int) -> None:
        self._clock += timedelta(seconds=seconds)
        self._sequence += 1

    def fetch_current(self, tags: Sequence[str]) -> AcquisitionBatch:
        requested = self._authorizer.validate(tags)
        events = [self._current_event(tag) for tag in requested]
        return AcquisitionBatch(
            acquired_at=self._clock,
            query_mode="current",
            source="synthetic",
            events=events,
        )

    def fetch_recorded(self, tags: Sequence[str], start: datetime, end: datetime) -> AcquisitionBatch:
        requested = self._authorizer.validate(tags)
        if end < start:
            raise ValueError("Historical end must not precede start")
        events: list[PiEvent] = []
        interval = timedelta(seconds=self._config.acquisition.expected_collection_interval_seconds)
        for tag in requested:
            configured = self._events_by_tag.get(tag)
            if configured:
                events.extend(event for event in configured if start <= event.pi_event_timestamp <= end)
                continue
            timestamp = start
            while timestamp <= end:
                events.append(self._synthetic_event(tag, timestamp, int((timestamp - start) / interval)))
                timestamp += interval
        return AcquisitionBatch(
            acquired_at=self._clock,
            query_mode="recorded",
            source="synthetic",
            events=sorted(events, key=lambda event: (event.pi_event_timestamp, event.tag_name)),
        )

    def _current_event(self, tag: str) -> PiEvent:
        configured = self._events_by_tag.get(tag)
        if configured:
            eligible = [event for event in configured if event.pi_event_timestamp <= self._clock]
            if eligible:
                return max(eligible, key=lambda event: event.pi_event_timestamp)
        return self._synthetic_event(tag, self._clock, self._sequence)

    def _synthetic_event(self, tag: str, timestamp: datetime, sequence: int) -> PiEvent:
        suffix = self._config.suffix_for_tag(tag)
        if suffix == "FileRead":
            value = f"SYNTHETIC_E3_{timestamp:%Y%m%d_%H%M}.etl"
        elif suffix == "E3Server.Status":
            value = "SYNTHETIC_RUNNING"
        else:
            value = round(10.0 + sequence + (sum(map(ord, suffix)) % 17) / 10, 3)
        return PiEvent(
            tag_name=tag,
            pi_event_timestamp=timestamp,
            value=value,
            quality="Good",
            questionable=False,
            substituted=False,
            unit=None,
            source="synthetic",
        )
