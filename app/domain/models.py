from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class SampleClassification(str, Enum):
    NEW = "NEW"
    REPEATED = "REPEATED"
    DELAYED = "DELAYED"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    INVALID = "INVALID"
    STALE = "STALE"
    MISSING = "MISSING"


class RedundancyState(str, Enum):
    INITIALIZING = "INITIALIZING"
    ACTIVE_COLLECTING = "ACTIVE_COLLECTING"
    STALE = "STALE"
    SWITCHOVER_SUSPECTED = "SWITCHOVER_SUSPECTED"
    POST_SWITCHOVER_STABILIZING = "POST_SWITCHOVER_STABILIZING"
    ACQUISITION_FAILURE = "ACQUISITION_FAILURE"
    APPLICATION_UNAVAILABLE = "APPLICATION_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class PiEvent(BaseModel):
    """An event exactly as received from PI, apart from transport conversion."""

    model_config = ConfigDict(extra="forbid")

    tag_name: str
    pi_event_timestamp: datetime
    value: Any
    quality: str | None = None
    questionable: bool = False
    substituted: bool = False
    unit: str | None = None
    source: str = "pi"


class AcquisitionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acquisition_id: str = Field(default_factory=lambda: str(uuid4()))
    acquired_at: datetime
    query_mode: str
    source: str
    events: list[PiEvent] = Field(default_factory=list)


class NormalizedEvent(BaseModel):
    """A PI event with original value preserved and an optional typed value."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    acquisition_id: str
    tag_name: str
    group_id: str
    metric_suffix: str
    pi_event_timestamp: datetime
    acquired_at: datetime
    raw_value: Any
    converted_value: float | str | datetime | None = None
    expected_type: str
    quality: str | None
    questionable: bool
    substituted: bool
    unit: str | None
    valid_for_analysis: bool
    rejection_reason: str | None = None
    source: str


class GroupObservation(BaseModel):
    """The current 26-tag view of one logical redundant group."""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    observed_at: datetime
    collection_timestamp: datetime | None
    metrics: dict[str, float | str | datetime | None]
    metric_validity: dict[str, bool]
    quality_ratio: float
    missing_metrics: list[str] = Field(default_factory=list)


class GroupRuntimeState(BaseModel):
    """Persisted state needed to evaluate the next observation without guessing."""

    model_config = ConfigDict(extra="forbid")

    group_id: str
    state: RedundancyState = RedundancyState.INITIALIZING
    state_since: datetime
    previous_collection_timestamp: datetime | None = None
    previous_metrics: dict[str, float | str | datetime | None] = Field(default_factory=dict)
    valid_samples: int = 0
    stable_samples: int = 0
    stabilizing_until: datetime | None = None
    session_id: str | None = None
    last_quality_ratio: float = Field(default=0, ge=0, le=1)
    last_missing_metrics: list[str] = Field(default_factory=list)


class StateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime: GroupRuntimeState
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    classification: SampleClassification
    start_new_session: bool = False
    session_reason: str | None = None


class AlarmRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alarm_key: str
    group_id: str
    title: str
    severity: str
    condition: str
    evidence: list[str]
    risk_index: int | None = None
    confidence: float = Field(ge=0, le=1)
    status: str = "OPEN"
    created_at: datetime
    updated_at: datetime


class OperationalSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(default_factory=lambda: str(uuid4()))
    group_id: str
    started_at: datetime
    ended_at: datetime | None = None
    reason: str
