from __future__ import annotations

import logging

from app.config.models import NotificationsConfig
from app.domain.models import AlarmRecord


class NotificationService:
    """Phase 4 local sink. Corporate channels can replace this without changing alarms."""

    _ORDER = {"info": 1, "warning": 2, "critical": 3}

    def __init__(self, config: NotificationsConfig, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger

    def notify(self, alarms: list[AlarmRecord]) -> None:
        if not self._config.enabled:
            return
        for alarm in alarms:
            if self._ORDER[alarm.severity] >= self._ORDER[self._config.minimum_severity]:
                self._logger.warning(
                    "Operational notification emitted",
                    extra={"event": "notification_emitted", "group_id": alarm.group_id},
                )
