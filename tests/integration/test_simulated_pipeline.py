from datetime import datetime, timezone
import warnings

import pytest

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")
from fastapi.testclient import TestClient

from app.acquisition.interfaces import PiClient, PiClientError
from app.acquisition.simulated import SimulatedPiClient
from app.dashboard.app import create_dashboard_app
from app.domain.models import AcquisitionBatch
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
