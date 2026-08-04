from __future__ import annotations

from datetime import datetime, timezone
from statistics import median

from app.config.models import PhaseFiveConfig
from app.domain.models import HistoricalQualityReport, ModelComparisonResult
from app.storage.sqlite import SqliteRepository


class PhaseFiveUnavailable(RuntimeError):
    pass


class ShadowModelComparisonService:
    """Compare transparent robust scores with Isolation Forest; never opens alarms."""

    def __init__(self, config: PhaseFiveConfig) -> None:
        self._config = config

    def run(self, repository: SqliteRepository) -> tuple[list[HistoricalQualityReport], list[ModelComparisonResult]]:
        reports = repository.historical_quality_reports(
            self._config.minimum_valid_ratio, self._config.minimum_feature_rows
        )
        results: list[ModelComparisonResult] = []
        adjusted_reports: list[HistoricalQualityReport] = []
        for report in reports:
            if not report.ready_for_phase5:
                adjusted_reports.append(report)
                continue
            rows = repository.phase5_feature_rows(report.group_id, self._config.feature_metric_suffixes)
            if len(rows) < self._config.minimum_feature_rows:
                adjusted_reports.append(
                    report.model_copy(
                        update={
                            "ready_for_phase5": False,
                            "limitations": [
                                *report.limitations,
                                "insufficient complete, time-aligned feature rows for model comparison",
                            ],
                        }
                    )
                )
                continue
            result = self._compare(report.group_id, rows)
            repository.store_model_experiment(result)
            results.append(result)
            adjusted_reports.append(report)
        return adjusted_reports, results

    def supervised_readiness(self, repository: SqliteRepository) -> dict[str, object]:
        labels = repository.list_operational_labels()
        by_type: dict[str, int] = {}
        for label in labels:
            by_type[label["label_type"]] = by_type.get(label["label_type"], 0) + 1
        return {
            "label_count": len(labels),
            "labels_by_type": by_type,
            "ready": len(labels) >= 50 and len(by_type) >= 3,
            "limitation": "supervised learning remains a study until labels cover confirmed normal and incident periods",
        }

    def _compare(self, group_id: str, rows: list[dict[str, float]]) -> ModelComparisonResult:
        try:
            from sklearn.ensemble import IsolationForest
        except ImportError as exc:
            raise PhaseFiveUnavailable("Install the phase5 optional dependency to compare non-supervised models") from exc
        features = self._config.feature_metric_suffixes
        raw_matrix = [[row[feature] for feature in features] for row in rows]
        centers = [median(row[index] for row in raw_matrix) for index in range(len(features))]
        scales = [
            max(median(abs(row[index] - centers[index]) for row in raw_matrix) * 1.4826, abs(centers[index]) * 0.05, 1e-9)
            for index in range(len(features))
        ]
        normalized = [[(value - centers[index]) / scales[index] for index, value in enumerate(row)] for row in raw_matrix]
        robust_flags = [max(abs(value) for value in row) >= 3.5 for row in normalized]
        model = IsolationForest(contamination=self._config.contamination, random_state=42, n_jobs=1)
        isolation_flags = [prediction == -1 for prediction in model.fit_predict(normalized)]
        explanations: list[dict[str, float | str]] = []
        for index, (robust, isolated) in enumerate(zip(robust_flags, isolation_flags)):
            if not (robust or isolated):
                continue
            leading_index = max(range(len(features)), key=lambda item: abs(normalized[index][item]))
            explanations.append(
                {
                    "row_index": float(index),
                    "leading_metric": features[leading_index],
                    "robust_z_score": round(normalized[index][leading_index], 4),
                    "robust_detector": "true" if robust else "false",
                    "isolation_forest": "true" if isolated else "false",
                }
            )
            if len(explanations) == 50:
                break
        return ModelComparisonResult(
            group_id=group_id,
            calculated_at=datetime.now(timezone.utc),
            deployment_mode=self._config.deployment_mode,
            sample_count=len(rows),
            feature_metric_suffixes=features,
            robust_outliers=sum(robust_flags),
            isolation_forest_outliers=sum(isolation_flags),
            agreed_outliers=sum(robust and isolated for robust, isolated in zip(robust_flags, isolation_flags)),
            explanations=explanations,
            limitations=[
                "shadow-mode result does not influence alarms, risk, or production decisions",
                "model output is statistical evidence, not a confirmed root cause",
            ],
        )
