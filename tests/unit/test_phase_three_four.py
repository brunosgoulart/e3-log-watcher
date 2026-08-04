from datetime import datetime, timedelta, timezone
import warnings

import pytest

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
from fastapi.testclient import TestClient

from app.backtesting.service import BacktestSample, BacktestService
from app.dashboard.app import create_dashboard_app
from app.detection.service import PhaseTwoAnalysisService
from app.domain.models import GroupObservation, RedundancyState
from app.forecasting.service import ForecastService


def _observation(at, value=10.0):
    return GroupObservation(
        group_id="COGCGPRO12",
        observed_at=at,
        source_timestamp=at,
        metrics={"E3Run.Occupancy": value, "E3Run.AvgScriptTime": value, "E3Run.CPU": value, "E3Run.Memory": value},
        metric_validity={},
        quality_ratio=1.0,
        missing_metrics=[],
    )


def test_short_horizon_forecast_requires_stable_linear_history(config):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = {"E3Run.Memory": [(start + timedelta(hours=index), 100 + 2 * index) for index in range(30)]}
    forecasts = ForecastService(config.forecasting).project("COGCGPRO12", "session-1", start + timedelta(hours=29), history)
    forecast = next(item for item in forecasts if item.metric_suffix == "E3Run.Memory")
    assert forecast.r_squared == pytest.approx(1.0)
    assert forecast.projected_value == pytest.approx(166.0)


def test_backtesting_evaluates_before_adding_current_sample(config):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        BacktestSample("COGCGPRO12", "session-1", RedundancyState.ACTIVE_COLLECTING, _observation(start + timedelta(minutes=index)))
        for index in range(30)
    ]
    samples.append(
        BacktestSample(
            "COGCGPRO12", "session-1", RedundancyState.ACTIVE_COLLECTING, _observation(start + timedelta(minutes=30), 90)
        )
    )
    run = BacktestService(config.backtesting, PhaseTwoAnalysisService(config.analysis)).run(samples)
    assert run.summary["alarms"] == 1
    assert run.events[0]["triggered_rules"] == ["script_processing_pressure"]


def test_admin_label_api_requires_environment_secret(config, repository, monkeypatch):
    client = TestClient(create_dashboard_app(repository, config))
    assert client.get("/health").json()["status"] == "degraded"
    payload = {
        "group_id": "COGCGPRO12",
        "started_at": "2026-01-01T00:00:00Z",
        "label_type": "switchover",
        "note": "synthetic test label",
    }
    assert client.post("/api/admin/labels", json=payload).status_code == 503
    monkeypatch.setenv(config.api.admin_api_key_env, "test-key")
    assert client.post("/api/admin/labels", json=payload, headers={"X-API-Key": "wrong"}).status_code == 403
    assert client.post("/api/admin/labels", json=payload, headers={"X-API-Key": "test-key"}).status_code == 201
    assert client.get("/api/labels?group_id=COGCGPRO12").json()[0]["label_type"] == "switchover"
