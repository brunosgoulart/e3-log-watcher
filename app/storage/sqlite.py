from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.models import (
    AcquisitionBatch,
    AlarmRecord,
    AnalysisResult,
    BaselineProfile,
    ForecastResult,
    GroupRuntimeState,
    HistoricalQualityReport,
    ModelComparisonResult,
    NormalizedEvent,
    OperationalSession,
    OperationalLabel,
    StateDecision,
)


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
                CREATE TABLE IF NOT EXISTS baseline_profiles (
                    baseline_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    metric_suffix TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    median REAL NOT NULL,
                    mad REAL NOT NULL,
                    lower_bound REAL NOT NULL,
                    upper_bound REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_baseline_group_session_metric
                    ON baseline_profiles(group_id, session_id, metric_suffix, calculated_at DESC);
                CREATE TABLE IF NOT EXISTS analysis_results (
                    analysis_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_id TEXT NOT NULL UNIQUE,
                    group_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    baseline_ready INTEGER NOT NULL,
                    risk_index INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    signals_json TEXT NOT NULL,
                    rules_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_analysis_group_calculated
                    ON analysis_results(group_id, calculated_at DESC);
                CREATE TABLE IF NOT EXISTS rule_alarm_states (
                    group_id TEXT NOT NULL,
                    rule_id TEXT NOT NULL,
                    consecutive_matches INTEGER NOT NULL,
                    consecutive_clears INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(group_id, rule_id)
                );
                CREATE TABLE IF NOT EXISTS forecasts (
                    forecast_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    metric_suffix TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    horizon_hours INTEGER NOT NULL,
                    sample_count INTEGER NOT NULL,
                    slope_per_hour REAL NOT NULL,
                    projected_value REAL NOT NULL,
                    r_squared REAL NOT NULL,
                    lower_projection REAL NOT NULL,
                    upper_projection REAL NOT NULL,
                    estimated_limit_time TEXT,
                    limitations_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_forecasts_group_metric ON forecasts(group_id, metric_suffix, calculated_at DESC);
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS backtest_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    session_id TEXT,
                    risk_index INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    triggered_rules_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES backtest_runs(run_id)
                );
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    calculated_at TEXT NOT NULL,
                    deployment_mode TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    feature_metrics_json TEXT NOT NULL,
                    robust_outliers INTEGER NOT NULL,
                    isolation_forest_outliers INTEGER NOT NULL,
                    agreed_outliers INTEGER NOT NULL,
                    explanations_json TEXT NOT NULL,
                    limitations_json TEXT NOT NULL
                );
                """
            )
            self._apply_removed_collection_timestamp_migration()

    def _apply_removed_collection_timestamp_migration(self) -> None:
        """Remove the retired textual tag and all derived state based on it once."""
        migration_id = "20260730_remove_collection_timestamp"
        existing = self._connection.execute(
            "SELECT 1 FROM schema_migrations WHERE migration_id = ?", (migration_id,)
        ).fetchone()
        if existing:
            return
        self._connection.execute("DELETE FROM raw_events WHERE tag_name LIKE '%.CollectionTimeStamp'")
        self._connection.execute("DELETE FROM normalized_events WHERE metric_suffix = 'CollectionTimeStamp'")
        # State, sessions and analytical results depended on the retired freshness signal.
        for table in ("redundancy_states", "operational_sessions", "baseline_profiles", "analysis_results", "rule_alarm_states", "forecasts", "alarms"):
            self._connection.execute(f"DELETE FROM {table}")
        self._connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?)", (migration_id, datetime.now(timezone.utc).isoformat())
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

    def recent_metric_values(self, group_id: str, metric_suffix: str, limit: int = 3) -> list[dict[str, Any]]:
        """Return the latest eligible numeric measurements for an alarm explanation."""
        with self._lock:
            rows = self._connection.execute(
                """SELECT pi_event_timestamp, converted_value_json
                   FROM normalized_events
                   WHERE group_id = ? AND metric_suffix = ?
                     AND valid_for_analysis = 1 AND converted_value_json IS NOT NULL
                   ORDER BY pi_event_timestamp DESC LIMIT ?""",
                (group_id, metric_suffix, limit),
            ).fetchall()
        measurements: list[dict[str, Any]] = []
        for row in rows:
            value = json.loads(row["converted_value_json"])
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                measurements.append({"timestamp": row["pi_event_timestamp"], "value": float(value)})
        return measurements

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

    def list_alarms(self, group_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM alarms"
        clauses: list[str] = []
        parameters: list[Any] = []
        if group_id:
            clauses.append("group_id = ?")
            parameters.append(group_id)
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
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

    def session_started_at(self, session_id: str) -> datetime | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT started_at FROM operational_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return datetime.fromisoformat(row["started_at"]) if row else None

    def numeric_history(
        self, group_id: str, started_at: datetime, exclude_acquisition_id: str | None = None
    ) -> dict[str, list[tuple[datetime, float]]]:
        sql = """
            SELECT metric_suffix, pi_event_timestamp, converted_value_json
            FROM normalized_events
            WHERE group_id = ? AND valid_for_analysis = 1 AND pi_event_timestamp >= ?
        """
        parameters: list[Any] = [group_id, started_at.isoformat()]
        if exclude_acquisition_id:
            sql += " AND acquisition_id <> ?"
            parameters.append(exclude_acquisition_id)
        sql += " ORDER BY pi_event_timestamp ASC"
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        values: dict[str, list[tuple[datetime, float]]] = {}
        for row in rows:
            value = json.loads(row["converted_value_json"])
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.setdefault(row["metric_suffix"], []).append(
                    (datetime.fromisoformat(row["pi_event_timestamp"]), float(value))
                )
        return values

    def store_baselines(self, profiles: list[BaselineProfile]) -> None:
        if not profiles:
            return
        rows = [
            (
                profile.group_id,
                profile.session_id,
                profile.metric_suffix,
                profile.calculated_at.isoformat(),
                profile.sample_count,
                profile.median,
                profile.mad,
                profile.lower_bound,
                profile.upper_bound,
            )
            for profile in profiles
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                """INSERT INTO baseline_profiles (
                    group_id, session_id, metric_suffix, calculated_at, sample_count,
                    median, mad, lower_bound, upper_bound
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def store_analysis_result(self, result: AnalysisResult) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT INTO analysis_results (
                    result_id, group_id, session_id, calculated_at, baseline_ready,
                    risk_index, confidence, signals_json, rules_json, limitations_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.result_id,
                    result.group_id,
                    result.session_id,
                    result.calculated_at.isoformat(),
                    int(result.baseline_ready),
                    result.risk_index,
                    result.confidence,
                    result.model_dump_json(include={"signals"}),
                    _json(result.triggered_rules),
                    _json(result.limitations),
                ),
            )

    def latest_analysis_by_group(self) -> dict[str, dict[str, Any]]:
        query = """
            SELECT current.group_id, current.risk_index, current.confidence,
                   current.baseline_ready, current.signals_json, current.rules_json, current.limitations_json
            FROM analysis_results AS current
            INNER JOIN (
                SELECT group_id, MAX(analysis_event_id) AS latest_id
                FROM analysis_results GROUP BY group_id
            ) AS latest ON current.analysis_event_id = latest.latest_id
        """
        with self._lock:
            rows = self._connection.execute(query).fetchall()
        return {
            row["group_id"]: {
                "risk_index": row["risk_index"],
                "confidence": row["confidence"],
                "baseline_ready": bool(row["baseline_ready"]),
                "signals": json.loads(row["signals_json"]).get("signals", []),
                "triggered_rules": json.loads(row["rules_json"]),
                "limitations": json.loads(row["limitations_json"]),
            }
            for row in rows
        }

    def get_rule_alarm_state(self, group_id: str, rule_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM rule_alarm_states WHERE group_id = ? AND rule_id = ?", (group_id, rule_id)
            ).fetchone()
        return dict(row) if row else None

    def save_rule_alarm_state(
        self,
        group_id: str,
        rule_id: str,
        consecutive_matches: int,
        consecutive_clears: int,
        status: str,
        updated_at: datetime,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT OR REPLACE INTO rule_alarm_states VALUES (?, ?, ?, ?, ?, ?)""",
                (group_id, rule_id, consecutive_matches, consecutive_clears, status, updated_at.isoformat()),
            )

    def resolve_alarm(self, alarm_key: str, updated_at: datetime) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE alarms SET status = 'RESOLVED', updated_at = ? WHERE alarm_key = ? AND status = 'OPEN'",
                (updated_at.isoformat(), alarm_key),
            )

    def store_forecasts(self, forecasts: list[ForecastResult]) -> None:
        if not forecasts:
            return
        rows = [
            (
                forecast.forecast_id,
                forecast.group_id,
                forecast.session_id,
                forecast.metric_suffix,
                forecast.calculated_at.isoformat(),
                forecast.horizon_hours,
                forecast.sample_count,
                forecast.slope_per_hour,
                forecast.projected_value,
                forecast.r_squared,
                forecast.lower_projection,
                forecast.upper_projection,
                forecast.estimated_limit_time.isoformat() if forecast.estimated_limit_time else None,
                _json(forecast.limitations),
            )
            for forecast in forecasts
        ]
        with self._lock, self._connection:
            self._connection.executemany("INSERT INTO forecasts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    def latest_forecasts(self, group_id: str | None = None) -> list[dict[str, Any]]:
        sql = """
            SELECT current.* FROM forecasts AS current
            INNER JOIN (
                SELECT group_id, metric_suffix, MAX(rowid) AS latest_id
                FROM forecasts GROUP BY group_id, metric_suffix
            ) AS latest ON current.rowid = latest.latest_id
        """
        parameters: tuple[Any, ...] = ()
        if group_id:
            sql += " WHERE current.group_id = ?"
            parameters = (group_id,)
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [dict(row) | {"limitations": json.loads(row["limitations_json"])} for row in rows]

    def create_operational_label(self, label: OperationalLabel) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO operational_labels VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    label.label_id,
                    label.group_id,
                    label.started_at.isoformat(),
                    label.ended_at.isoformat() if label.ended_at else None,
                    label.label_type,
                    label.note,
                    label.created_at.isoformat(),
                ),
            )

    def list_operational_labels(self, group_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM operational_labels"
        parameters: tuple[Any, ...] = ()
        if group_id:
            sql += " WHERE group_id = ?"
            parameters = (group_id,)
        sql += " ORDER BY started_at DESC"
        with self._lock:
            rows = self._connection.execute(sql, parameters).fetchall()
        return [dict(row) for row in rows]

    def record_backtest_run(self, run_id: str, started_at: datetime, ended_at: datetime, configuration: dict[str, Any], summary: dict[str, Any]) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO backtest_runs VALUES (?, ?, ?, ?, ?)",
                (run_id, started_at.isoformat(), ended_at.isoformat(), _json(configuration), _json(summary)),
            )

    def record_backtest_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        rows = [
            (
                run_id,
                event["group_id"],
                event["occurred_at"].isoformat(),
                event.get("session_id"),
                event["risk_index"],
                event["confidence"],
                _json(event["triggered_rules"]),
            )
            for event in events
        ]
        with self._lock, self._connection:
            self._connection.executemany(
                """INSERT INTO backtest_events (
                    run_id, group_id, occurred_at, session_id, risk_index, confidence, triggered_rules_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def latest_acquisition(self) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM acquisitions ORDER BY acquired_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def historical_quality_reports(self, minimum_valid_ratio: float, minimum_feature_rows: int) -> list[HistoricalQualityReport]:
        query = """
            SELECT group_id, COUNT(*) AS total_events,
                   SUM(CASE WHEN valid_for_analysis = 1 THEN 1 ELSE 0 END) AS valid_events,
                   COUNT(DISTINCT metric_suffix) AS distinct_metrics,
                   MIN(pi_event_timestamp) AS first_event_at, MAX(pi_event_timestamp) AS last_event_at
            FROM normalized_events GROUP BY group_id ORDER BY group_id
        """
        with self._lock:
            rows = self._connection.execute(query).fetchall()
        reports: list[HistoricalQualityReport] = []
        for row in rows:
            total = int(row["total_events"])
            valid = int(row["valid_events"] or 0)
            ratio = valid / total if total else 0.0
            limitations: list[str] = []
            if ratio < minimum_valid_ratio:
                limitations.append("valid PI quality ratio is below the configured Phase 5 minimum")
            if valid < minimum_feature_rows:
                limitations.append("insufficient valid historical events for a controlled model comparison")
            reports.append(
                HistoricalQualityReport(
                    group_id=row["group_id"],
                    total_events=total,
                    valid_events=valid,
                    valid_ratio=ratio,
                    distinct_metrics=int(row["distinct_metrics"]),
                    first_event_at=datetime.fromisoformat(row["first_event_at"]) if row["first_event_at"] else None,
                    last_event_at=datetime.fromisoformat(row["last_event_at"]) if row["last_event_at"] else None,
                    ready_for_phase5=not limitations,
                    limitations=limitations,
                )
            )
        return reports

    def phase5_feature_rows(self, group_id: str, metric_suffixes: list[str]) -> list[dict[str, float]]:
        """Return only same-timestamp, complete numeric rows for offline shadow comparison."""
        placeholders = ", ".join("?" for _ in metric_suffixes)
        query = f"""
            SELECT pi_event_timestamp, metric_suffix, converted_value_json
            FROM normalized_events
            WHERE group_id = ? AND valid_for_analysis = 1 AND metric_suffix IN ({placeholders})
            ORDER BY pi_event_timestamp ASC
        """
        with self._lock:
            rows = self._connection.execute(query, [group_id, *metric_suffixes]).fetchall()
        grouped: dict[str, dict[str, float]] = {}
        for row in rows:
            value = json.loads(row["converted_value_json"])
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                grouped.setdefault(row["pi_event_timestamp"], {})[row["metric_suffix"]] = float(value)
        return [values for values in grouped.values() if set(values) == set(metric_suffixes)]

    def store_model_experiment(self, result: ModelComparisonResult) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "INSERT INTO model_experiments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    result.experiment_id,
                    result.group_id,
                    result.calculated_at.isoformat(),
                    result.deployment_mode,
                    result.sample_count,
                    _json(result.feature_metric_suffixes),
                    result.robust_outliers,
                    result.isolation_forest_outliers,
                    result.agreed_outliers,
                    _json(result.explanations),
                    _json(result.limitations),
                ),
            )

    def latest_model_experiments(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM model_experiments ORDER BY calculated_at DESC"
            ).fetchall()
        return [
            dict(row)
            | {
                "feature_metrics": json.loads(row["feature_metrics_json"]),
                "explanations": json.loads(row["explanations_json"]),
                "limitations": json.loads(row["limitations_json"]),
            }
            for row in rows
        ]
