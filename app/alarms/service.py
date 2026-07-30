from __future__ import annotations

from app.domain.models import AlarmRecord, GroupObservation, RedundancyState, StateDecision
from app.storage.interfaces import MonitorRepository


class PhaseOneAlarmService:
    """Only data-state alarms in Phase 1; no performance diagnosis is claimed yet."""

    _TEMPLATES = {
        RedundancyState.ACQUISITION_FAILURE: ("Falha de aquisição do PI System", "critical"),
        RedundancyState.STALE: ("Dados stale", "warning"),
        RedundancyState.SWITCHOVER_SUSPECTED: ("Possível switchover", "info"),
        RedundancyState.APPLICATION_UNAVAILABLE: ("Possível indisponibilidade da aplicação", "critical"),
    }

    def synchronize(self, repository: MonitorRepository, decision: StateDecision, observation: GroupObservation) -> None:
        template = self._TEMPLATES.get(decision.runtime.state)
        if template is None:
            repository.resolve_state_alarms(decision.runtime.group_id, observation.observed_at)
            return
        title, severity = template
        alarm = AlarmRecord(
            alarm_key=f"state:{decision.runtime.group_id}:{decision.runtime.state.value}",
            group_id=decision.runtime.group_id,
            title=title,
            severity=severity,
            condition="; ".join(decision.evidence),
            evidence=decision.evidence,
            confidence=decision.confidence,
            created_at=observation.observed_at,
            updated_at=observation.observed_at,
        )
        repository.resolve_state_alarms(decision.runtime.group_id, observation.observed_at)
        repository.upsert_alarm(alarm)
