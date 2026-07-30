from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from app.domain.models import AcquisitionBatch


class PiClientError(RuntimeError):
    """A transport, authentication, SDK, or PI query error."""


class PiClient(ABC):
    """PI access contract. Analytics never imports a concrete PI implementation."""

    @abstractmethod
    def fetch_current(self, tags: Sequence[str]) -> AcquisitionBatch:
        raise NotImplementedError

    @abstractmethod
    def fetch_recorded(self, tags: Sequence[str], start: datetime, end: datetime) -> AcquisitionBatch:
        raise NotImplementedError
