"""Configuration loading for the epoch service (Service A).

All runtime behaviour (bind address, port, endpoint paths) is driven by a single
YAML config file. A different file can be supplied via the CONFIG_PATH
environment variable, otherwise the config shipped with the service is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    epoch_path: str
    health_path: str


def load_settings(path: str | os.PathLike | None = None) -> Settings:
    config_path = Path(path or os.environ.get("CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open() as f:
        raw = yaml.safe_load(f) or {}

    try:
        server = raw["server"]
        endpoints = raw["endpoints"]
        return Settings(
            host=str(server["host"]),
            port=int(server["port"]),
            epoch_path=str(endpoints["epoch"]),
            health_path=str(endpoints["health"]),
        )
    except KeyError as exc:
        raise ValueError(f"Missing required config key {exc} in {config_path}") from exc
