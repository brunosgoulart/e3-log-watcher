from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config.models import AcquisitionConfig, QualityConfig
from app.domain.models import PiEvent, SampleClassification


@dataclass(frozen=True)
class QualityAssessment:
    valid_for_analysis: bool
    rejection_reason: str | None


def assess_quality(event: PiEvent, policy: QualityConfig, acquisition: AcquisitionConfig) -> QualityAssessment:
    """Preserve all events; decide only whether one can contribute to analytics."""

    quality = event.quality
    if quality in policy.bad_quality_values and acquisition.reject_bad_values:
        return QualityAssessment(False, "bad_pi_quality")
    if event.questionable and acquisition.reject_questionable_values:
        return QualityAssessment(False, "questionable_pi_value")
    if event.substituted and acquisition.exclude_substituted_from_analysis:
        return QualityAssessment(False, "substituted_pi_value")
    return QualityAssessment(True, None)


def classify_source_timestamp(
    previous: datetime | None,
    current: datetime | None,
    observed_at: datetime,
    config: AcquisitionConfig,
) -> SampleClassification:
    if current is None:
        return SampleClassification.MISSING
    age_seconds = (observed_at - current).total_seconds()
    if age_seconds > config.stale_after_seconds:
        return SampleClassification.STALE
    if previous is None:
        return SampleClassification.DELAYED if age_seconds > config.delayed_after_seconds else SampleClassification.NEW
    if current < previous:
        return SampleClassification.OUT_OF_ORDER
    if current == previous:
        return SampleClassification.REPEATED
    return SampleClassification.DELAYED if age_seconds > config.delayed_after_seconds else SampleClassification.NEW
