from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from app.config.models import AppConfig


_ENV_TOKEN = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")


def _resolve_environment(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_environment(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_environment(item) for item in value]
    if isinstance(value, str):
        match = _ENV_TOKEN.fullmatch(value)
        if match:
            return os.getenv(match.group(1)) or None
    return value


def load_config(path: str | Path) -> AppConfig:
    """Load only safe YAML and resolve complete ${ENV_VAR} values."""

    with Path(path).open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError("Configuration root must be a mapping")
    return AppConfig.model_validate(_resolve_environment(data))
