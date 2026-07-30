from datetime import datetime, timedelta

from app.domain.models import GroupObservation, RedundancyState
from app.redundancy.state_machine import RedundancyStateMachine


def _observation(timestamp, collection_timestamp, uptime=100.0, errors=10.0, file_read="a.etl", status="RUNNING", quality=1.0):
    return GroupObservation(
        group_id="COGCGPRO12",
        observed_at=timestamp,
        collection_timestamp=collection_timestamp,
        metrics={
            "E3Run.UpTimeMinutes": uptime,
            "FileRead": file_read,
            "E3Server.Status": status,
            "E3Run.Errors": errors,
        },
        metric_validity={},
        quality_ratio=quality,
        missing_metrics=[],
    )


def test_new_samples_reach_active_collecting_after_minimum(config):
    machine = RedundancyStateMachine(config)
    first_time = datetime.fromisoformat("2026-01-01T12:00:00-03:00")
    runtime = None
    for index in range(3):
        at = first_time + timedelta(seconds=60 * index)
        decision = machine.update(runtime, _observation(at, at), True)
        runtime = decision.runtime
    assert runtime.state == RedundancyState.ACTIVE_COLLECTING
    assert runtime.valid_samples == 3


def test_stale_then_reset_and_file_change_is_possible_switchover(config):
    machine = RedundancyStateMachine(config)
    start = datetime.fromisoformat("2026-01-01T12:00:00-03:00")
    first = machine.update(None, _observation(start, start, uptime=100, file_read="before.etl"), True)
    stale = machine.update(
        first.runtime,
        _observation(start + timedelta(seconds=400), start, uptime=100, file_read="before.etl"),
        True,
    )
    assert stale.runtime.state == RedundancyState.STALE
    recovered_at = start + timedelta(seconds=410)
    switched = machine.update(
        stale.runtime,
        _observation(recovered_at, recovered_at, uptime=2, file_read="after.etl"),
        True,
    )
    assert switched.runtime.state == RedundancyState.SWITCHOVER_SUSPECTED
    assert switched.start_new_session is True
    assert "E3Run.UpTimeMinutes decreased" in switched.evidence


def test_counter_reset_is_recorded_as_switchover_evidence(config):
    machine = RedundancyStateMachine(config)
    start = datetime.fromisoformat("2026-01-01T12:00:00-03:00")
    first = machine.update(None, _observation(start, start, errors=100, file_read="before.etl"), True)
    changed_at = start + timedelta(seconds=60)
    decision = machine.update(
        first.runtime,
        _observation(changed_at, changed_at, errors=1, file_read="after.etl"),
        True,
    )
    assert decision.runtime.state == RedundancyState.SWITCHOVER_SUSPECTED
    assert "E3Run.Errors decreased" in decision.evidence


def test_low_quality_and_out_of_order_are_unknown(config):
    machine = RedundancyStateMachine(config)
    start = datetime.fromisoformat("2026-01-01T12:00:00-03:00")
    first = machine.update(None, _observation(start, start), True)
    low_quality = machine.update(first.runtime, _observation(start + timedelta(seconds=60), start + timedelta(seconds=60), quality=0.2), True)
    assert low_quality.runtime.state == RedundancyState.UNKNOWN
    out_of_order = machine.update(
        first.runtime,
        _observation(start + timedelta(seconds=60), start - timedelta(seconds=60)),
        True,
    )
    assert out_of_order.runtime.state == RedundancyState.UNKNOWN
