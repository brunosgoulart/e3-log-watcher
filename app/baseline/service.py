from __future__ import annotations

from datetime import datetime
from statistics import median

from app.config.models import AnalysisConfig
from app.domain.models import BaselineProfile


class RobustBaselineBuilder:
    """Median/MAD profiles; no ML and no data from another operational session."""

    def __init__(self, config: AnalysisConfig) -> None:
        self._config = config

    def build(
        self,
        group_id: str,
        session_id: str,
        calculated_at: datetime,
        history: dict[str, list[tuple[datetime, float]]],
    ) -> list[BaselineProfile]:
        profiles: list[BaselineProfile] = []
        for suffix, points in history.items():
            values = [value for _, value in points]
            if len(values) < self._config.baseline_minimum_samples:
                continue
            center = median(values)
            mad = median(abs(value - center) for value in values)
            # The relative width prevents a zero-MAD steady signal from causing
            # an unbounded z-score due only to representation precision.
            scale = max(1.4826 * mad, abs(center) * self._config.minimum_relative_baseline_width, 1e-9)
            width = self._config.robust_z_threshold * scale
            profiles.append(
                BaselineProfile(
                    group_id=group_id,
                    session_id=session_id,
                    metric_suffix=suffix,
                    calculated_at=calculated_at,
                    sample_count=len(values),
                    median=center,
                    mad=mad,
                    # The monitored counters and resource metrics cannot be negative.
                    # Clamp the statistical interval so the dashboard never presents
                    # an impossible expected range below zero.
                    lower_bound=max(0.0, center - width),
                    upper_bound=center + width,
                )
            )
        return profiles
