from datetime import datetime

from app.domain.models import AcquisitionBatch, PiEvent
from app.normalization.normalizer import EventNormalizer


def test_invalid_value_is_preserved_without_zero_substitution(config):
    event = PiEvent(
        tag_name="CSEO.COGCGPRO12.E3Run.CPU",
        pi_event_timestamp=datetime.fromisoformat("2026-01-01T12:00:00-03:00"),
        value="not-a-number",
        quality="Good",
        source="synthetic",
    )
    batch = AcquisitionBatch(acquired_at=event.pi_event_timestamp, query_mode="current", source="synthetic", events=[event])
    normalized = EventNormalizer(config).normalize_event(event, batch)
    assert normalized.raw_value == "not-a-number"
    assert normalized.converted_value is None
    assert not normalized.valid_for_analysis
    assert normalized.rejection_reason == "expected_number"


def test_questionable_value_is_retained_when_config_allows_it(config):
    event = PiEvent(
        tag_name="CSEO.COGCGPRO12.E3Run.CPU",
        pi_event_timestamp=datetime.fromisoformat("2026-01-01T12:00:00-03:00"),
        value=12.5,
        quality="Good",
        questionable=True,
        source="synthetic",
    )
    batch = AcquisitionBatch(acquired_at=event.pi_event_timestamp, query_mode="current", source="synthetic", events=[event])
    normalized = EventNormalizer(config).normalize_event(event, batch)
    assert normalized.questionable is True
    assert normalized.valid_for_analysis is True
