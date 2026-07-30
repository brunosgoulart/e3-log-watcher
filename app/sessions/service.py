from __future__ import annotations

from app.domain.models import GroupObservation, OperationalSession, StateDecision
from app.storage.interfaces import MonitorRepository


class SessionService:
    """Sessions are changed only on explicit evidence, never between arbitrary samples."""

    def apply(self, repository: MonitorRepository, decision: StateDecision, observation: GroupObservation) -> StateDecision:
        if not decision.start_new_session:
            return decision
        started_at = observation.collection_timestamp or observation.observed_at
        if decision.runtime.session_id:
            repository.close_active_session(decision.runtime.group_id, started_at)
        session = OperationalSession(
            group_id=decision.runtime.group_id,
            started_at=started_at,
            reason=decision.session_reason or "state_transition",
        )
        repository.open_session(session)
        decision.runtime.session_id = session.session_id
        return decision
