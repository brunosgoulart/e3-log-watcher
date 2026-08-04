from __future__ import annotations

from datetime import datetime, timedelta
from math import sqrt

from app.config.models import ForecastingConfig
from app.domain.models import ForecastResult


class ForecastService:
    """Linear, short-horizon forecasts gated by fit quality and valid-session data."""

    def __init__(self, config: ForecastingConfig) -> None:
        self._config = config

    def project(
        self,
        group_id: str,
        session_id: str,
        calculated_at: datetime,
        history: dict[str, list[tuple[datetime, float]]],
    ) -> list[ForecastResult]:
        if not self._config.enabled:
            return []
        projections: list[ForecastResult] = []
        for suffix in self._config.metric_suffixes:
            points = history.get(suffix, [])
            if len(points) < self._config.minimum_samples:
                continue
            projection = self._fit(group_id, session_id, suffix, calculated_at, points)
            if projection and projection.r_squared >= self._config.minimum_r_squared:
                projections.append(projection)
        return projections

    def _fit(
        self,
        group_id: str,
        session_id: str,
        suffix: str,
        calculated_at: datetime,
        points: list[tuple[datetime, float]],
    ) -> ForecastResult | None:
        origin = points[0][0]
        xs = [(timestamp - origin).total_seconds() / 3600 for timestamp, _ in points]
        ys = [value for _, value in points]
        x_mean = sum(xs) / len(xs)
        y_mean = sum(ys) / len(ys)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        if denominator <= 0:
            return None
        slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
        intercept = y_mean - slope * x_mean
        fitted = [intercept + slope * x for x in xs]
        residual_sum = sum((actual - expected) ** 2 for actual, expected in zip(ys, fitted))
        total_sum = sum((actual - y_mean) ** 2 for actual in ys)
        r_squared = max(0.0, 1.0 - residual_sum / total_sum) if total_sum > 0 else 0.0
        horizon = self._config.horizon_hours
        projected = intercept + slope * (xs[-1] + horizon)
        residual_scale = sqrt(residual_sum / max(1, len(ys) - 2))
        margin = 1.96 * residual_scale
        limit = self._config.static_limits.get(suffix)
        limit_time = None
        if limit is not None and slope > 0 and projected >= limit:
            hours_to_limit = (limit - ys[-1]) / slope
            if 0 <= hours_to_limit <= horizon:
                limit_time = calculated_at + timedelta(hours=hours_to_limit)
        return ForecastResult(
            group_id=group_id,
            session_id=session_id,
            metric_suffix=suffix,
            calculated_at=calculated_at,
            horizon_hours=horizon,
            sample_count=len(points),
            slope_per_hour=slope,
            projected_value=projected,
            r_squared=r_squared,
            lower_projection=projected - margin,
            upper_projection=projected + margin,
            estimated_limit_time=limit_time,
            limitations=["linear projection limited to configured short horizon", "units and static limits require operational approval"],
        )
