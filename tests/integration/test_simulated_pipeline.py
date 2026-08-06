from datetime import datetime, timedelta, timezone
import warnings

import pytest

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
from fastapi.testclient import TestClient

from app.acquisition.interfaces import PiClient, PiClientError
from app.acquisition.simulated import SimulatedPiClient
from app.dashboard.app import _expected_range, _format_timestamp, create_dashboard_app
from app.domain.models import AcquisitionBatch, AlarmRecord, AnalysisResult, MetricSignal, NormalizedEvent
from app.monitoring.service import MonitoringService
from app.observability.logging import configure_logging


def test_simulated_current_acquisition_persists_and_renders_dashboard(config, repository):
    client = SimulatedPiClient(config, clock=datetime(2026, 1, 1, tzinfo=timezone.utc))
    service = MonitoringService(config, client, repository, configure_logging("WARNING"))
    assert service.run_once() == 75
    client.advance(60)
    service.run_once()
    client.advance(60)
    service.run_once()
    cards = repository.latest_state_cards()
    assert len(cards) == 3
    assert all(card["state"] == "ACTIVE_COLLECTING" for card in cards)
    assert len(repository.metric_history("COGCGPRO12")) == 75
    response = TestClient(create_dashboard_app(repository, config)).get("/")
    assert response.status_code == 200
    assert "COGCGPRO1/COGCGPRO2" in response.text
    assert "Coleta ativa" in response.text


def test_historical_import_does_not_change_online_runtime(config, repository):
    client = SimulatedPiClient(config, clock=datetime(2026, 1, 1, tzinfo=timezone.utc))
    service = MonitoringService(config, client, repository, configure_logging("WARNING"))
    count = service.import_historical(
        datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 1, 1, 0, 2, tzinfo=timezone.utc)
    )
    assert count == 75 * 3
    assert repository.latest_runtime_states() == {}


class FailingPiClient(PiClient):
    def fetch_current(self, tags):
        raise PiClientError("synthetic failure")

    def fetch_recorded(self, tags, start, end) -> AcquisitionBatch:
        raise PiClientError("synthetic failure")


def test_acquisition_failure_is_not_reported_as_application_degradation(config, repository):
    service = MonitoringService(config, FailingPiClient(), repository, configure_logging("WARNING"))
    assert service.run_once() == 0
    cards = repository.latest_state_cards()
    assert len(cards) == 3
    assert all(card["state"] == "ACQUISITION_FAILURE" for card in cards)
    assert all(alarm["title"] == "Falha de aquisição do PI System" for alarm in repository.list_alarms())


def test_dashboard_overview_highlights_active_alarms_deviations_and_health(config, repository):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    repository.store_normalized_events(
        [
            NormalizedEvent(
                acquisition_id=f"acquisition-{index}",
                tag_name="CSEO.COGCGPRO12.E3Run.CPU",
                group_id="COGCGPRO12",
                metric_suffix="E3Run.CPU",
                pi_event_timestamp=now + timedelta(minutes=index),
                acquired_at=now + timedelta(minutes=index),
                raw_value=value,
                converted_value=value,
                expected_type="number",
                quality="Good",
                questionable=False,
                substituted=False,
                unit=None,
                valid_for_analysis=True,
                source="synthetic",
            )
            for index, value in enumerate((80.0, 88.0, 92.0, 95.0))
        ]
    )
    repository.upsert_alarm(
        AlarmRecord(
            alarm_key="analysis:COGCGPRO12:script_processing_pressure",
            group_id="COGCGPRO12",
            title="Possível degradação no processamento de scripts",
            severity="warning",
            condition="E3Run.CPU=92; baseline [20, 40]; z robusto=6.1; tendência=12.0%/h",
            evidence=["E3Run.CPU=92", "tendência=12.0%/h"],
            risk_index=30,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
    )
    repository.store_analysis_result(
        AnalysisResult(
            group_id="COGCGPRO12",
            session_id="session-1",
            calculated_at=now,
            baseline_ready=True,
            risk_index=30,
            confidence=0.9,
            signals=[
                MetricSignal(
                    metric_suffix="E3Run.CPU",
                    value=92,
                    baseline_median=30,
                    lower_bound=20,
                    upper_bound=40,
                    robust_z_score=6.1,
                    trend_relative_per_hour=0.12,
                    high_anomaly=True,
                    rising_trend=True,
                )
            ],
            triggered_rules=["script_processing_pressure"],
        )
    )
    client = TestClient(create_dashboard_app(repository, config))
    response = client.get("/")
    assert response.status_code == 200
    assert "Resumo de saúde do sistema" in response.text
    assert "Alarmes ativos (1)" in response.text
    assert "Medições recentes" in response.text
    assert "95 % · 92 % · 88 %" in response.text
    assert "Lista cronológica: mais recente primeiro" not in response.text
    assert "z robusto=6.1" not in response.text
    assert "data-alarm-sort='updated'" in response.text
    assert "active-alarm-sort-status" not in response.text
    assert "Principais desvios e incrementos em observação" in response.text
    assert "E3Run.CPU" in response.text
    assert client.get("/api/alarms/active").json()[0]["status"] == "OPEN"
    assert client.get("/api/alarms?status=RESOLVED").json() == []
    detail = client.get("/groups/COGCGPRO12")
    assert "Buscar" in detail.text
    assert "data-sort='timestamp'" in detail.text
    assert "Limites configurados: normal até 40 %" in detail.text
    assert "metric-highlight limit-critical" in detail.text


def test_dashboard_formats_timestamp_in_configured_timezone():
    assert _format_timestamp("2026-08-06T18:49:02.157012+00:00", "America/Sao_Paulo") == "06/08/2026 - 15:49:02"
    assert _expected_range(-10, 755.5029) == "0 à 755,5029"
