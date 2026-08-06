from datetime import datetime, timedelta, timezone

from app.alarms.composite import CompositeAlarmService
from app.detection.service import PhaseTwoAnalysisService
from app.domain.models import AnalysisResult, GroupObservation, MetricSignal


def _observation(at, occupancy=90.0, script_time=90.0, cpu=90.0):
    return GroupObservation(
        group_id="COGCGPRO12",
        observed_at=at,
        source_timestamp=at,
        metrics={"E3Run.Occupancy": occupancy, "E3Run.AvgScriptTime": script_time, "E3Run.CPU": cpu},
        metric_validity={},
        quality_ratio=1.0,
        missing_metrics=[],
    )


def test_baseline_uses_only_prior_session_samples_and_triggers_composite_rule(config):
    service = PhaseTwoAnalysisService(config.analysis)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = {
        suffix: [(start + timedelta(minutes=index), 10.0) for index in range(30)]
        for suffix in ("E3Run.Occupancy", "E3Run.AvgScriptTime", "E3Run.CPU")
    }
    profiles, result, rules = service.evaluate(
        _observation(start + timedelta(minutes=30)), "session-1", history
    )
    assert len(profiles) == 3
    assert result.baseline_ready is True
    assert result.risk_index == 30
    assert [rule.rule_id for rule in rules] == ["script_processing_pressure"]
    assert all(signal.high_anomaly for signal in result.signals)


def test_current_outlier_does_not_create_baseline_with_insufficient_prior_samples(config):
    service = PhaseTwoAnalysisService(config.analysis)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = {"E3Run.CPU": [(start + timedelta(minutes=index), 10.0) for index in range(29)]}
    profiles, result, rules = service.evaluate(_observation(start + timedelta(minutes=29)), "session-1", history)
    assert profiles == []
    assert result.baseline_ready is False
    assert rules == []
    assert result.risk_index == 0


def test_baseline_expected_range_never_goes_below_zero(config):
    service = PhaseTwoAnalysisService(config.analysis)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = {"E3Run.CPU": [(start + timedelta(minutes=index), 0.0) for index in range(30)]}
    profiles, _, _ = service.evaluate(_observation(start + timedelta(minutes=30), cpu=0.0), "session-1", history)
    assert profiles[0].lower_bound == 0.0


def test_composite_alarm_requires_persistence_and_hysteresis(config, repository):
    rule = next(rule for rule in config.analysis.composite_rules if rule.rule_id == "script_processing_pressure")
    alarm_service = CompositeAlarmService(config.analysis)
    at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    signal = MetricSignal(
        metric_suffix="E3Run.Occupancy",
        value=90,
        baseline_median=10,
        lower_bound=5,
        upper_bound=15,
        robust_z_score=16,
        high_anomaly=True,
        rising_trend=True,
        trend_relative_per_hour=1.0,
    )
    result = AnalysisResult(
        group_id="COGCGPRO12",
        session_id="session-1",
        calculated_at=at,
        baseline_ready=True,
        risk_index=30,
        confidence=0.8,
        signals=[signal],
        triggered_rules=[rule.rule_id],
    )
    for offset in range(config.analysis.alarm_open_persistence):
        alarm_service.synchronize(repository, result.model_copy(update={"calculated_at": at + timedelta(minutes=offset)}), [rule])
    assert repository.list_alarms()[0]["status"] == "OPEN"
    cleared = result.model_copy(update={"triggered_rules": [], "risk_index": 0})
    for offset in range(config.analysis.alarm_resolve_hysteresis):
        alarm_service.synchronize(
            repository,
            cleared.model_copy(update={"calculated_at": at + timedelta(minutes=10 + offset)}),
            [],
        )
    assert repository.list_alarms()[0]["status"] == "RESOLVED"
