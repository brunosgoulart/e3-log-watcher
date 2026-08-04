from __future__ import annotations

from app.config.models import AnalysisConfig, CompositeRuleConfig
from app.domain.models import AlarmRecord, AnalysisResult, MetricSignal
from app.storage.sqlite import SqliteRepository


class CompositeAlarmService:
    """Persistence and hysteresis for statistically supported Phase 2 alarms."""

    def __init__(self, config: AnalysisConfig) -> None:
        self._config = config

    def synchronize(
        self,
        repository: SqliteRepository,
        result: AnalysisResult,
        rules: list[CompositeRuleConfig],
    ) -> list[AlarmRecord]:
        opened: list[AlarmRecord] = []
        triggered_ids = {rule.rule_id for rule in rules}
        rule_by_id = {rule.rule_id: rule for rule in self._config.composite_rules}
        for rule_id, rule in rule_by_id.items():
            previous = repository.get_rule_alarm_state(result.group_id, rule_id) or {
                "consecutive_matches": 0,
                "consecutive_clears": 0,
                "status": "CLOSED",
            }
            is_triggered = rule_id in triggered_ids
            matches = int(previous["consecutive_matches"]) + 1 if is_triggered else 0
            clears = 0 if is_triggered else int(previous["consecutive_clears"]) + 1
            status = str(previous["status"])
            alarm_key = f"analysis:{result.group_id}:{rule_id}"
            if is_triggered and matches >= self._config.alarm_open_persistence:
                status = "OPEN"
                alarm = self._alarm_record(alarm_key, rule, result)
                repository.upsert_alarm(alarm)
                opened.append(alarm)
            elif not is_triggered and status == "OPEN" and clears >= self._config.alarm_resolve_hysteresis:
                status = "CLOSED"
                repository.resolve_alarm(alarm_key, result.calculated_at)
            repository.save_rule_alarm_state(
                result.group_id, rule_id, matches, clears, status, result.calculated_at
            )
        return opened

    @staticmethod
    def _alarm_record(alarm_key: str, rule: CompositeRuleConfig, result: AnalysisResult) -> AlarmRecord:
        related = [signal for signal in result.signals if signal.metric_suffix in rule.metric_suffixes]
        evidence = [_format_signal(signal) for signal in related if signal.high_anomaly or signal.rising_trend]
        return AlarmRecord(
            alarm_key=alarm_key,
            group_id=result.group_id,
            title=rule.title,
            severity=rule.severity,
            condition="; ".join(evidence),
            evidence=evidence,
            risk_index=result.risk_index,
            confidence=result.confidence,
            created_at=result.calculated_at,
            updated_at=result.calculated_at,
        )


def _format_signal(signal: MetricSignal) -> str:
    fragments = [
        f"{signal.metric_suffix}={signal.value:.4g}",
        f"baseline [{signal.lower_bound:.4g}, {signal.upper_bound:.4g}]",
        f"z robusto={signal.robust_z_score:.2f}",
    ]
    if signal.rising_trend and signal.trend_relative_per_hour is not None:
        fragments.append(f"tendência={signal.trend_relative_per_hour:.1%}/h")
    return "; ".join(fragments)
