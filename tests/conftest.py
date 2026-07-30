from pathlib import Path

import pytest

from app.config.loader import load_config
from app.storage.sqlite import SqliteRepository


@pytest.fixture()
def config():
    return load_config(Path(__file__).parents[1] / "configs" / "phase1.yaml")


@pytest.fixture()
def repository(tmp_path):
    repo = SqliteRepository(tmp_path / "monitor.db")
    yield repo
    repo.close()
