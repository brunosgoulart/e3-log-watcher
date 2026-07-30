from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain.models import AcquisitionBatch, AlarmRecord, GroupRuntimeState, NormalizedEvent, OperationalSession, PiEvent, StateDecision


def _json(value: Any) -> str:
    return json.dumps(value, default=lambda item: item.isoformat() if isinstance(item, datetime) else str(item), ensure_ascii=False)


class SqliteRepository:
    """Local Phase 1 repository; SQLite details do not leak into analytical services."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS acquisitions (
                    acquisition_id TEXT PRIMARY KEY,
                    acquired_at TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    query_mode TEXT NOT NULL,
                    requested_tags_json TEXT NOT NULL,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS raw_events (
                    raw_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    acquisition_id TEXT NOT NULL,
                    tag_name TEXT NOT NULL,
                    pi_event_timestamp TEXT NOT NULL,
                    raw_value_json TEXT NOT NULL,
                    quality TEXT,
                    questionable INTEGER NOT NULL,
                    substituted INTEGER NOT NULL,
                    unit TEXT,
                    source TEXT NOT NULL,
                    FOREIGN KEY(acquisition_id) REFERENCES acquisitions(acquisition_id)
                );
                CREATE INDEX IF NOT EXISTS ix_raw_events_tag_time ON raw_events(tag_name, pi_event_timestamp);
                CREATE TABLE IF NOT EXISTS normalized_events (
                    event_id TEXT PRIMARY KEY,
                    acquisition_id TEXT NOT NULL,
                    tag_name TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    metric_suffix TEXT NOT NULL,
                    pi_event_timestamp TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    raw_value_json TEXT NOT NULL,
                    converted_value_json TEXT,
                    expected_type TEXT NOT NULL,
                    quality TEXT,
                    questionable INTEGER NOT NULL,
                    substituted INTEGER NOT NULL,
                    unit TEXT,
                    valid_for_analysis INTEGER NOT NULL,
                    rejection_reason TEXT,
                    source TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_normalized_group_metric_time
                    ON normalized_events(group_id, metric_suffix, pi_event_timestamp);
                CREATE TABLE IF NOT EXISTS operational_sessions (
                    session_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    reason TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_sessions_group_start ON operational_sessions(group_id, started_at);
                CREATE TABLE IF NOT EXISTS redundancy_states (
                    state_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    state TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_json TEXT NOT NULL,
                    runtime_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_states_group_observed ON redundancy_states(group_id, observed_at DESC);
                CREATE TABLE IF NOT EXISTS alarms (
                    alarm_key TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    condition_text TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    risk_index INTEGER,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operational_labels (
                    label_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    label_type TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def record_acquisition(
        self,
        acquisition_id: str,
        acquired_at: datetime,
        success: bool,
        source: str,
        query_mode: str,
        requested_tags: list[str],
        error_message: str | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT OR REPLACE INTO acquisitions VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (acquisition_id, acquired_at.isoformat(), int(success), source, query_mode, _json(requested_tags), error_message),
            )

    def store_raw_events(self, batch: AcquisitionBatch) -> None:
        rows = [
            (
                batch.acquisition_id,
                event.tag_name,
                event.pi_event_timestamp.isoformat(),
                _json(event.value),
                event.quality,
                int(event.questionable),
                int(event.substituted),
                event.unit,
                event.source,
            )
            for event in batch.events
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                """INSERT INTO raw_events (
                    acquisition_id, tag_name, pi_event_timestamp, raw_value_json, quality,
                    questionable, substituted, unit, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def store_normalized_events(self, events: list[NormalizedEvent]) -> None:
        rows = [
            (
                event.event_id,
                event.acquisition_id,
                event.tag_name,
                event.group_id,
                event.metric_suffix,
                event.pi_event_timestamp.isoformat(),
                event.acquired_at.isoformat(),
                _json(event.raw_value),
                _json(event.converted_value) if event.converted_value is not None else None,
                event.expected_type,
                event.quality,
                int(event.questionable),
                int(event.substituted),
                event.unit,
                int(event.valid_for_analysis),
                event.rejection_reason,
                event.source,
            )
            for event in events
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                """INSERT INTO normalized_events VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                rows,
            )

    def open_session(self, session: OperationalSession) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO operational_sessions VALUES (?, ?, ?, ?, ?)",
                (session.session_id, session.group_id, session.started_at.isoformat(), None, session.reason),
            )

    def close_active_session(self, group_id: str, ended_at: datetime) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE operational_sessions SET ended_at = ?
                   WHERE group_id = ? AND ended_at IS NULL""",
                (ended_at.isoformat(), group_id),
            )

    def record_state(self, decision: StateDecision, observed_at: datetime) -> None:
        runtime_json = decision.runtime.model_dump_json()
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO redundancy_states (
                    group_id, observed_at, state, classification, confidence, evidence_json, runtime_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.runtime.group_id,
                    observed_at.isoformat(),
                    decision.runtime.state.value,
                    decision.classification.value,
                    decision.confidence,
                    _json(decision.evidence),
                    runtime_json,
                ),
            )

    def latest_runtime_states(self) -> dict[str, GroupRuntimeState]:
        query = """
            SELECT state.group_id, state.runtime_json
            FROM redundancy_states AS state
            INNER JOIN (
                SELECT group_id, MAX(state_event_id) AS latest_id
                FROM redundancy_states GROUP BY group_id
            ) AS latest ON state.state_event_id = latest.latest_id
        """
        with self._lock:
            rows = self._connection.execute(query).fetchall()
        return {row["group_id"]: GroupRuntimeState.model_validate_json(row["runtime_json"]) for row in rows}

    def latest_state_cards(self) -> list[dict[str, Any]]:
        query = """
            SELECT state.group_id, state.observed_at, state.state, state.classification,
                   state.confidence, state.evidence_json, state.runtime_json
            FROM redundancy_states AS state
            INNER JOIN (
                SELECT group_id, MAX(state_event_id) AS latest_id
                FROM redundancy_states GROUP BY group_id
            ) AS latest ON state.state_event_id = latest.latest_id
            ORDER BY state.group_id
        """
        with self._lock:
            rows = self._connection.execute(query).fetchall()
        return [
            {
                "group_id": row["group_id"],
                "observed_at": row["observed_at"],
                "state": row["state"],
                "classification": row["classification"],
                "confidence": row["confidence"],
                "evidence": json.loads(row["evidence_json"]),
                "runtime": json.loads(row["runtime_json"]),
            }
            for row in rows
        ]

    def metric_history(self, group_id: str, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """SELECT metric_suffix, pi_event_timestamp, converted_value_json, quality, valid_for_analysis
                   FROM normalized_events WHERE group_id = ?
                   ORDER BY pi_event_timestamp DESC LIMIT ?""",
                (group_id, limit),
            ).fetchall()
        return [
            {
                "metric_suffix": row["metric_suffix"],
                "pi_event_timestamp": row["pi_event_timestamp"],
                "converted_value": json.loads(row["converted_value_json"]) if row["converted_value_json"] else None,
                "quality": row["quality"],
                "valid_for_analysis": bool(row["valid_for_analysis"]),
            }
            for row in rows
        ]

    def upsert_alarm(self, alarm: AlarmRecord) -> None:
        with self._lock, self._connection:
            existing = self._connection.execute("SELECT created_at FROM alarms WHERE alarm_key = ?", (alarm.alarm_key,)).fetchone()
            created_at = existing["created_at"] if existing else alarm.created_at.isoformat()
            self._connection.execute(
                """INSERT OR REPLACE INTO alarms VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alarm.alarm_key,
                    alarm.group_id,
                    alarm.title,
                    alarm.severity,
                    alarm.condition,
                    _json(alarm.evidence),
                    alarm.risk_index,
                    alarm.confidence,
                    alarm.status,
                    created_at,
                    alarm.updated_at.isoformat(),
                ),
            )

    def resolve_state_alarms(self, group_id: str, updated_at: datetime) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """UPDATE alarms SET status = 'RESOLVED', updated_at = ?
                   WHERE group_id = ? AND alarm_key LIKE 'state:%' AND status = 'OPEN'""",
                (updated_at.isoformat(), group_id),
            )

    def list_alarms(self, group_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alarms"
        parameters: tuple[Any, ...] = ()
        if group_id:
            sql += " WHERE group_id = ?"
            parameters = (group_id,)
        sql += " ORDER BY status = 'OPEN' DESC, updated_at DESC"
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [
            {
                "alarm_key": row["alarm_key"],
                "group_id": row["group_id"],
                "title": row["title"],
                "severity": row["severity"],
                "condition": row["condition_text"],
                "evidence": json.loads(row["evidence_json"]),
                "risk_index": row["risk_index"],
                "confidence": row["confidence"],
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]
