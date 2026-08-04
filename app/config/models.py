from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


METRIC_SUFFIXES: tuple[str, ...] = (
    "E3Run.AvgScriptTime",
    "E3Run.CPU",
    "E3Run.DiscardedEvents",
    "E3Run.Errors",
    "E3Run.ErrorsPerMinute",
    "E3Run.HDL",
    "E3Run.Memory",
    "E3Run.Occupancy",
    "E3Run.PageFaults",
    "E3Run.PendingEvents",
    "E3Run.PVT",
    "E3Run.RemoteDiscardedPerMinute",
    "E3Run.RemoteDiscardPercent",
    "E3Run.RemoteHandledPerMinute",
    "E3Run.RemotePending",
    "E3Run.TRD",
    "E3Run.UpTimeMinutes",
    "E3Server.CPU",
    "E3Server.HDL",
    "E3Server.PVT",
    "E3Server.Status",
    "FileRead",
    "ioQueue.AvgDelay",
    "ioQueue.Pending",
    "TotalTime",
)


class PiSystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_method: Literal["pi_af_sdk"]
    af_server: str | None = None
    data_archive: str | None = None
    af_sdk_assembly_path: str | None = None
    authentication_method: Literal["windows_integrated"]
    request_timeout_seconds: int = Field(gt=0)
    retry_attempts: int = Field(ge=0)
    retry_delay_seconds: int = Field(ge=0)
    query_mode: Literal["recorded", "interpolated", "summary"]
    timezone: str


class AcquisitionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    online_interval_seconds: int = Field(gt=0)
    historical_batch_hours: int = Field(gt=0)
    overlap_seconds: int = Field(ge=0)
    expected_collection_interval_seconds: int = Field(gt=0)
    delayed_after_seconds: int = Field(gt=0)
    stale_after_seconds: int = Field(gt=0)
    switchover_suspect_after_seconds: int = Field(gt=0)
    stabilization_seconds: int = Field(gt=0)
    unavailable_after_seconds: int = Field(gt=0)
    minimum_valid_samples: int = Field(gt=0)
    maximum_events_per_query: int = Field(gt=0)
    reject_questionable_values: bool
    reject_bad_values: bool
    exclude_substituted_from_analysis: bool
    store_raw_values: bool


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sqlite_path: str


class DashboardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_seconds: int = Field(gt=0)
    history_hours: int = Field(gt=0)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str
    structured: bool


class ServerGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    pi_prefix: str
    physical_servers: list[str] = Field(min_length=2, max_length=2)
    redundancy_mode: Literal["hot_standby"]


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_type: Literal["number", "text", "datetime", "unknown"]
    category: str
    unit: str | None = None
    enabled: bool


class RedundancyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unavailable_status_values: list[str]
    reset_sensitive_metric_suffixes: list[str]
    minimum_switchover_evidence: int = Field(ge=1)


class QualityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_quality_values: list[str]
    bad_quality_values: list[str]
    minimum_group_quality_ratio: float = Field(ge=0, le=1)


class CompositeRuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    severity: Literal["info", "warning", "critical"]
    metric_suffixes: list[str] = Field(min_length=2)
    minimum_confirmations: int = Field(ge=1)
    risk_weight: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def confirmations_fit_metrics(self) -> "CompositeRuleConfig":
        if self.minimum_confirmations > len(self.metric_suffixes):
            raise ValueError("minimum_confirmations cannot exceed the metrics in a composite rule")
        return self


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_minimum_samples: int = Field(ge=5)
    robust_z_threshold: float = Field(gt=0)
    minimum_relative_baseline_width: float = Field(gt=0)
    trend_window_samples: int = Field(ge=3)
    minimum_relative_slope_per_hour: float = Field(gt=0)
    alarm_open_persistence: int = Field(ge=1)
    alarm_resolve_hysteresis: int = Field(ge=1)
    composite_rules: list[CompositeRuleConfig]


class ForecastingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    minimum_samples: int = Field(ge=5)
    horizon_hours: int = Field(gt=0)
    minimum_r_squared: float = Field(ge=0, le=1)
    metric_suffixes: list[str]
    static_limits: dict[str, float]


class BacktestingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warmup_samples: int = Field(ge=1)
    include_stabilizing: bool
    report_timezone: str


class ApiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_unauthenticated_read: bool
    admin_api_key_env: str


class NotificationsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    minimum_severity: Literal["info", "warning", "critical"]


class PhaseFiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_mode: Literal["shadow", "controlled"]
    minimum_valid_ratio: float = Field(ge=0, le=1)
    minimum_feature_rows: int = Field(ge=30)
    contamination: float = Field(gt=0, lt=0.5)
    feature_metric_suffixes: list[str] = Field(min_length=2)
    allow_alarm_influence: bool


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pi_system: PiSystemConfig
    acquisition: AcquisitionConfig
    storage: StorageConfig
    dashboard: DashboardConfig
    logging: LoggingConfig
    server_groups: list[ServerGroup]
    metric_catalog: dict[str, MetricDefinition]
    redundancy: RedundancyConfig
    quality: QualityConfig
    analysis: AnalysisConfig
    forecasting: ForecastingConfig
    backtesting: BacktestingConfig
    api: ApiConfig
    notifications: NotificationsConfig
    phase5: PhaseFiveConfig
    authorized_tags: list[str]

    @model_validator(mode="after")
    def enforce_closed_catalogue(self) -> "AppConfig":
        if len(self.server_groups) != 3:
            raise ValueError("exactly three logical server groups are required")
        group_ids = [group.group_id for group in self.server_groups]
        prefixes = [group.pi_prefix for group in self.server_groups]
        if len(set(group_ids)) != 3 or len(set(prefixes)) != 3:
            raise ValueError("server group identifiers and PI prefixes must be unique")
        if set(self.metric_catalog) != set(METRIC_SUFFIXES):
            raise ValueError("metric_catalog must contain exactly the 26 approved suffixes")
        if len(self.authorized_tags) != 75 or len(set(self.authorized_tags)) != 75:
            raise ValueError("authorized_tags must contain exactly 75 unique numeric tags")
        expected_tags = {
            f"{group.pi_prefix}.{suffix}"
            for group in self.server_groups
            for suffix in METRIC_SUFFIXES
        }
        if set(self.authorized_tags) != expected_tags:
            raise ValueError("authorized_tags must be the exact closed set for the three groups")
        for group in self.server_groups:
            group_tags = [tag for tag in self.authorized_tags if tag.startswith(f"{group.pi_prefix}.")]
            if len(group_tags) != 25:
                raise ValueError(f"{group.group_id} must have exactly 25 tags")
        unknown_reset_metrics = set(self.redundancy.reset_sensitive_metric_suffixes) - set(METRIC_SUFFIXES)
        if unknown_reset_metrics:
            raise ValueError(f"reset metrics are not authorized: {sorted(unknown_reset_metrics)}")
        for rule in self.analysis.composite_rules:
            unknown_rule_metrics = set(rule.metric_suffixes) - set(METRIC_SUFFIXES)
            if unknown_rule_metrics:
                raise ValueError(f"rule {rule.rule_id} has unknown metrics: {sorted(unknown_rule_metrics)}")
        unknown_forecast_metrics = set(self.forecasting.metric_suffixes) - set(METRIC_SUFFIXES)
        if unknown_forecast_metrics:
            raise ValueError(f"forecasting has unknown metrics: {sorted(unknown_forecast_metrics)}")
        unknown_limits = set(self.forecasting.static_limits) - set(self.forecasting.metric_suffixes)
        if unknown_limits:
                raise ValueError(f"forecasting limits are not enabled metrics: {sorted(unknown_limits)}")
        unknown_phase5_metrics = set(self.phase5.feature_metric_suffixes) - set(METRIC_SUFFIXES)
        if unknown_phase5_metrics:
            raise ValueError(f"phase5 has unknown metrics: {sorted(unknown_phase5_metrics)}")
        if self.phase5.deployment_mode == "shadow" and self.phase5.allow_alarm_influence:
            raise ValueError("shadow Phase 5 mode cannot influence alarms")
        return self

    def group_for_tag(self, tag_name: str) -> ServerGroup:
        for group in self.server_groups:
            prefix = f"{group.pi_prefix}."
            if tag_name.startswith(prefix):
                return group
        raise KeyError(f"Tag is not mapped to an authorized group: {tag_name}")

    def suffix_for_tag(self, tag_name: str) -> str:
        group = self.group_for_tag(tag_name)
        return tag_name.removeprefix(f"{group.pi_prefix}.")
