from __future__ import annotations

from datetime import datetime

from app.baseline.service import RobustBaselineBuilder
from app.config.models import AnalysisConfig, CompositeRuleConfig
from app.domain.models import AnalysisResult, BaselineProfile, GroupObservation, MetricSignal
from app.scoring.risk import calculate_risk


class PhaseTwoAnalysisService:
    """Statistical Phase 2 analysis, explicitly gated by data/session readiness."""

    def __init__(self, config: AnalysisConfig) -> None:
        self._config = config
        self._baseline_builder = RobustBaselineBuilder(config)

    def evaluate(
        self,
        observation: GroupObservation,
        session_id: str,
        historical_values: dict[str, list[tuple[datetime, float]]],
    ) -> tuple[list[BaselineProfile], AnalysisResult, list[CompositeRuleConfig]]:
        profiles = self._baseline_builder.build(
            observation.group_id, session_id, observation.observed_at, historical_values
        )
        profile_by_metric = {profile.metric_suffix: profile for profile in profiles}
        signals: list[MetricSignal] = []
        for suffix, current in observation.metrics.items():
            if not isinstance(current, (int, float)) or isinstance(current, bool):
                continue
            profile = profile_by_metric.get(suffix)
            if profile is None:
                continue
            scale = max((profile.upper_bound - profile.median) / self._config.robust_z_threshold, 1e-9)
            robust_z = (float(current) - profile.median) / scale
            trend = self._relative_slope_per_hour(
                historical_values.get(suffix, []), observation.observed_at, float(current), profile.median
            )
            signals.append(
                MetricSignal(
                    metric_suffix=suffix,
                    value=float(current),
                    baseline_median=profile.median,
                    lower_bound=profile.lower_bound,
                    upper_bound=profile.upper_bound,
                    robust_z_score=robust_z,
                    trend_relative_per_hour=trend,
                    high_anomaly=float(current) > profile.upper_bound,
                    rising_trend=trend is not None and trend >= self._config.minimum_relative_slope_per_hour,
                )
            )
        triggered = self._triggered_rules(signals)
        baseline_ready = bool(profiles)
        limitations: list[str] = []
        if not baseline_ready:
            limitations.append("insufficient valid samples in the current operational session")
        if observation.missing_metrics:
            limitations.append("one or more authorized metrics are missing or rejected by quality policy")
        confidence = self._confidence(profiles, observation.quality_ratio)
        result = AnalysisResult(
            group_id=observation.group_id,
            session_id=session_id,
            calculated_at=observation.observed_at,
            baseline_ready=baseline_ready,
            risk_index=calculate_risk(triggered),
            confidence=confidence,
            signals=signals,
            triggered_rules=[rule.rule_id for rule in triggered],
            limitations=limitations,
        )
        return profiles, result, triggered

    def _triggered_rules(self, signals: list[MetricSignal]) -> list[CompositeRuleConfig]:
        by_suffix = {signal.metric_suffix: signal for signal in signals}
        triggered: list[CompositeRuleConfig] = []
        for rule in self._config.composite_rules:
            confirmations = sum(
                1
                for suffix in rule.metric_suffixes
                if (signal := by_suffix.get(suffix)) is not None
                and (
                    float(signal.value) > rule.minimum_values[suffix]
                    if suffix in rule.minimum_values
                    else signal.high_anomaly or signal.rising_trend
                )
            )
            if confirmations >= rule.minimum_confirmations:
                triggered.append(rule)
        return triggered

    def _relative_slope_per_hour(
        self,
        historical: list[tuple[datetime, float]],
        current_time: datetime,
        current_value: float,
        baseline_median: float,
    ) -> float | None:
        points = [*historical[-(self._config.trend_window_samples - 1) :], (current_time, current_value)]
        if len(points) < self._config.trend_window_samples:
            return None
        origin = points[0][0]
        xs = [(timestamp - origin).total_seconds() / 3600 for timestamp, _ in points]
        ys = [value for _, value in points]
        denominator = sum((x - sum(xs) / len(xs)) ** 2 for x in xs)
        if denominator <= 0:
            return None
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        slope_per_hour = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
        return slope_per_hour / max(abs(baseline_median), 1e-9)

    def _confidence(self, profiles: list[BaselineProfile], quality_ratio: float) -> float:
        if not profiles:
            return 0.0
        sample_component = sum(
            min(1.0, profile.sample_count / (self._config.baseline_minimum_samples * 2)) for profile in profiles
        ) / len(profiles)
        return min(1.0, sample_component * quality_ratio)
