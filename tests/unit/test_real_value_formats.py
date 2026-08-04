from datetime import datetime

from app.domain.models import AcquisitionBatch, PiEvent
from app.normalization.normalizer import EventNormalizer


def test_pi_comma_decimal_is_normalized_without_changing_raw_value(config):
    timestamp = datetime.fromisoformat("2026-07-30T11:00:00-03:00")
    event = PiEvent(
        tag_name="CSEO.COGCGPRO12.TotalTime",
        pi_event_timestamp=timestamp,
        value="0,25",
        quality="Good",
        source="synthetic",
    )
    normalized = EventNormalizer(config).normalize_event(
        event,
        AcquisitionBatch(acquired_at=timestamp, query_mode="current", source="synthetic", events=[event]),
    )
    assert normalized.raw_value == "0,25"
    assert normalized.converted_value == 0.25
    assert normalized.valid_for_analysis
