import pytest

from app.phase5.service import ShadowModelComparisonService


def test_shadow_comparison_is_explainable_and_cannot_influence_alarms(config):
    pytest.importorskip("sklearn")
    rows = [
        {
            "E3Run.CPU": 10.0,
            "E3Run.Memory": 100.0,
            "E3Run.Occupancy": 20.0,
            "E3Run.AvgScriptTime": 5.0,
            "ioQueue.Pending": 1.0,
        }
        for _ in range(250)
    ]
    rows.append(
        {
            "E3Run.CPU": 95.0,
            "E3Run.Memory": 900.0,
            "E3Run.Occupancy": 95.0,
            "E3Run.AvgScriptTime": 90.0,
            "ioQueue.Pending": 100.0,
        }
    )
    result = ShadowModelComparisonService(config.phase5)._compare("COGCGPRO12", rows)
    assert result.deployment_mode == "shadow"
    assert result.robust_outliers >= 1
    assert result.explanations
    assert any("does not influence alarms" in item for item in result.limitations)
