from __future__ import annotations

from datetime import datetime
from numbers import Real
from zoneinfo import ZoneInfo

from app.config.models import AppConfig, MetricDefinition
from app.data_quality.service import assess_quality
from app.domain.models import AcquisitionBatch, GroupObservation, NormalizedEvent, PiEvent


class EventNormalizer:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def normalize_batch(self, batch: AcquisitionBatch) -> list[NormalizedEvent]:
        return [self.normalize_event(event, batch) for event in batch.events]

    def normalize_event(self, event: PiEvent, batch: AcquisitionBatch) -> NormalizedEvent:
        group = self._config.group_for_tag(event.tag_name)
        suffix = self._config.suffix_for_tag(event.tag_name)
        definition = self._config.metric_catalog[suffix]
        converted, conversion_error = self._convert(event.value, definition)
        quality = assess_quality(event, self._config.quality, self._config.acquisition)
        valid_for_analysis = quality.valid_for_analysis and conversion_error is None
        return NormalizedEvent(
            acquisition_id=batch.acquisition_id,
            tag_name=event.tag_name,
            group_id=group.group_id,
            metric_suffix=suffix,
            pi_event_timestamp=event.pi_event_timestamp,
            acquired_at=batch.acquired_at,
            raw_value=event.value,
            converted_value=converted,
            expected_type=definition.expected_type,
            quality=event.quality,
            questionable=event.questionable,
            substituted=event.substituted,
            unit=event.unit or definition.unit,
            valid_for_analysis=valid_for_analysis,
            rejection_reason=quality.rejection_reason or conversion_error,
            source=event.source,
        )

    def build_observations(self, events: list[NormalizedEvent]) -> list[GroupObservation]:
        observations: list[GroupObservation] = []
        for group in self._config.server_groups:
            group_events = [event for event in events if event.group_id == group.group_id]
            latest_by_suffix: dict[str, NormalizedEvent] = {}
            for event in group_events:
                existing = latest_by_suffix.get(event.metric_suffix)
                if existing is None or event.pi_event_timestamp > existing.pi_event_timestamp:
                    latest_by_suffix[event.metric_suffix] = event
            metrics = {suffix: event.converted_value for suffix, event in latest_by_suffix.items()}
            metric_validity = {suffix: event.valid_for_analysis for suffix, event in latest_by_suffix.items()}
            missing = [suffix for suffix in self._config.metric_catalog if suffix not in latest_by_suffix]
            collection = metrics.get("CollectionTimeStamp")
            collection_timestamp = collection if isinstance(collection, datetime) else None
            valid_count = sum(metric_validity.values())
            quality_ratio = valid_count / len(self._config.metric_catalog)
            observed_at = max((event.acquired_at for event in group_events), default=events[0].acquired_at)
            observations.append(
                GroupObservation(
                    group_id=group.group_id,
                    observed_at=observed_at,
                    collection_timestamp=collection_timestamp,
                    metrics=metrics,
                    metric_validity=metric_validity,
                    quality_ratio=quality_ratio,
                    missing_metrics=missing,
                )
            )
        return observations

    def _convert(self, value: object, definition: MetricDefinition) -> tuple[float | str | datetime | None, str | None]:
        expected_type = definition.expected_type
        if value is None:
            return None, "null_value"
        if expected_type == "number":
            if isinstance(value, bool):
                return None, "expected_number"
            if isinstance(value, Real):
                return float(value), None
            if isinstance(value, str):
                try:
                    return float(value), None
                except ValueError:
                    pass
            return None, "expected_number"
        if expected_type == "text":
            return (value, None) if isinstance(value, str) else (None, "expected_text")
        if expected_type == "datetime":
            if isinstance(value, datetime):
                return self._with_timezone(value), None
            if isinstance(value, str):
                try:
                    return self._with_timezone(datetime.fromisoformat(value.replace("Z", "+00:00"))), None
                except ValueError:
                    pass
            return None, "expected_iso_datetime"
        if isinstance(value, Real) and not isinstance(value, bool):
            return float(value), None
        if isinstance(value, str):
            return value, None
        return None, "unsupported_unknown_type"

    def _with_timezone(self, value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=ZoneInfo(self._config.pi_system.timezone))
