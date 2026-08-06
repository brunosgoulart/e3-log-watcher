from __future__ import annotations

from app.config.models import AnalysisConfig, OperationalLimitConfig
from app.domain.models import AlarmRecord, GroupObservation
from app.storage.interfaces import MonitorRepository


class OperationalLimitAlarmService:
    """Apply approved static limits without disabling dynamic baseline analysis."""

    _RISK_BY_PRIORITY = {"critical": 60, "high": 40, "medium": 25, "low": 10}

    def __init__(self, config: AnalysisConfig) -> None:
        self._config = config

    def synchronize(self, repository: MonitorRepository, observation: GroupObservation) -> list[AlarmRecord]:
        opened: list[AlarmRecord] = []
        for suffix, limit in self._config.operational_limits.items():
            previous = repository.get_rule_alarm_state(observation.group_id, f"operational_limit:{suffix}") or {
                "consecutive_matches": 0,
                "consecutive_clears": 0,
                "status": "CLOSED",
            }
            value = observation.metrics.get(suffix)
            valid = observation.metric_validity.get(suffix, True)
            level = self._level(value, valid, limit)
            matches = int(previous["consecutive_matches"]) + 1 if level else 0
            clears = 0 if level else int(previous["consecutive_clears"]) + 1
            status = str(previous["status"])
            alarm_key = f"operational:{observation.group_id}:{suffix}"
            if level and matches >= self._config.alarm_open_persistence:
                status = "OPEN"
                alarm = self._alarm_record(alarm_key, observation, suffix, float(value), level, limit)
                repository.upsert_alarm(alarm)
                opened.append(alarm)
            elif not level and status == "OPEN" and clears >= self._config.alarm_resolve_hysteresis:
                status = "CLOSED"
                repository.resolve_alarm(alarm_key, observation.observed_at)
            repository.save_rule_alarm_state(
                observation.group_id,
                f"operational_limit:{suffix}",
                matches,
                clears,
                status,
                observation.observed_at,
            )
        return opened

    @staticmethod
    def _level(value: object, valid: bool, limit: OperationalLimitConfig) -> str | None:
        if not valid or not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if float(value) > limit.critical_above:
            return "critical"
        if float(value) > limit.attention_above:
            return "attention"
        return None

    def _alarm_record(
        self,
        alarm_key: str,
        observation: GroupObservation,
        suffix: str,
        value: float,
        level: str,
        limit: OperationalLimitConfig,
    ) -> AlarmRecord:
        priority = limit.priority_overrides.get(observation.group_id, limit.priority)
        severity = "critical" if level == "critical" else "warning"
        evidence = [
            f"{suffix}={value:.6g}",
            f"atenção acima de {limit.attention_above:.6g} {limit.unit}",
            f"crítico acima de {limit.critical_above:.6g} {limit.unit}",
            f"prioridade={priority}",
        ]
        return AlarmRecord(
            alarm_key=alarm_key,
            group_id=observation.group_id,
            title=f"Limite operacional excedido: {suffix}",
            severity=severity,
            condition="; ".join(evidence),
            evidence=evidence,
            risk_index=self._RISK_BY_PRIORITY[priority],
            confidence=observation.quality_ratio,
            created_at=observation.observed_at,
            updated_at=observation.observed_at,
        )
