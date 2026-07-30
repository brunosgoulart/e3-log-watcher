from __future__ import annotations

from collections.abc import Iterable

from app.config.models import AppConfig


class UnauthorizedTagError(ValueError):
    pass


class TagAuthorizer:
    """Closed-list enforcement applied before every PI SDK call."""

    def __init__(self, config: AppConfig) -> None:
        self._authorized = frozenset(config.authorized_tags)

    def validate(self, tags: Iterable[str]) -> list[str]:
        requested = list(tags)
        rejected = sorted(set(requested) - self._authorized)
        if rejected:
            raise UnauthorizedTagError(f"Unauthorized PI tag request: {rejected}")
        if len(requested) != len(set(requested)):
            raise ValueError("PI tag request contains duplicate tags")
        return requested
