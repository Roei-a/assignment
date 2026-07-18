"""Configuration loading for now-time-service (Service B).

Runtime behaviour (bind address, port, endpoint paths, timezone, and the URL of
the downstream epoch-service) is driven by a single YAML config file. A
different file can be supplied via CONFIG_PATH.

The one value that differs by environment — the epoch-service URL — can be
overridden with the EPOCH_SERVICE_URL environment variable (used by Docker
Compose to point at the Compose DNS name), so a single config file serves both
host and container use.
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
    now_path: str
    now_epoch_path: str
    health_path: str
    epoch_service_url: str
    default_timezone: str


def load_settings(path: str | os.PathLike | None = None) -> Settings:
    config_path = Path(path or os.environ.get("CONFIG_PATH") or DEFAULT_CONFIG_PATH)
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open() as f:
        raw = yaml.safe_load(f) or {}

    try:
        server = raw["server"]
        endpoints = raw["endpoints"]
        dependencies = raw["dependencies"]
        # The time section is optional; timezone defaults to UTC when omitted.
        time_cfg = raw.get("time") or {}
        # EPOCH_SERVICE_URL (if set) overrides the file value — this is the only
        # setting that differs between host and container environments.
        epoch_service_url = os.environ.get("EPOCH_SERVICE_URL") or dependencies["epoch_service_url"]
        return Settings(
            host=str(server["host"]),
            port=int(server["port"]),
            now_path=str(endpoints["now"]),
            now_epoch_path=str(endpoints["now_epoch"]),
            health_path=str(endpoints["health"]),
            epoch_service_url=str(epoch_service_url).rstrip("/"),
            default_timezone=str(time_cfg.get("default_timezone", "UTC")),
        )
    except KeyError as exc:
        raise ValueError(f"Missing required config key {exc} in {config_path}") from exc
