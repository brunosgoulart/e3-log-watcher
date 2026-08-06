from datetime import datetime, timedelta, timezone

from app.alarms.operational_limits import OperationalLimitAlarmService
from app.domain.models import GroupObservation


def _observation(at: datetime, cpu: float) -> GroupObservation:
    return GroupObservation(
        group_id="COGCGPRO12",
        observed_at=at,
        source_timestamp=at,
        metrics={"E3Run.CPU": cpu},
        metric_validity={"E3Run.CPU": True},
        quality_ratio=1.0,
        missing_metrics=[],
    )


def test_operational_limit_opens_after_five_samples_escalates_and_resolves(config, repository):
    service = OperationalLimitAlarmService(config.analysis)
    started_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for offset in range(5):
        service.synchronize(repository, _observation(started_at + timedelta(minutes=offset), 55.0))

    alarms = repository.list_alarms()
    assert len(alarms) == 1
    assert alarms[0]["title"] == "Limite operacional excedido: E3Run.CPU"
    assert alarms[0]["severity"] == "warning"
    assert alarms[0]["risk_index"] == 40
    assert alarms[0]["evidence"][0].startswith("E3Run.CPU=")

    service.synchronize(repository, _observation(started_at + timedelta(minutes=5), 70.0))
    assert repository.list_alarms()[0]["severity"] == "critical"

    for offset in range(config.analysis.alarm_resolve_hysteresis):
        service.synchronize(repository, _observation(started_at + timedelta(minutes=6 + offset), 40.0))
    assert repository.list_alarms()[0]["status"] == "RESOLVED"
