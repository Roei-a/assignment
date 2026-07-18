"""Integration tests for the running Compose environment.

Expects both services to be up (make up / docker compose up -d --wait):
  - epoch-service (Service A) on http://localhost:8080
  - now-time-service (Service B) on http://localhost:8081

Run with: make integration-test
"""

from __future__ import annotations

import os
import time
from datetime import datetime

import httpx

EPOCH_SERVICE_URL = os.environ.get("EPOCH_SERVICE_URL", "http://localhost:8080")
NOW_TIME_SERVICE_URL = os.environ.get("NOW_TIME_SERVICE_URL", "http://localhost:8081")
CLOCK_TOLERANCE_SECONDS = 30


def test_epoch_service_converts_dates() -> None:
    response = httpx.post(f"{EPOCH_SERVICE_URL}/epoch", json={"date": "2026-06-15T10:00:00Z"})
    assert response.status_code == 200
    assert response.json() == {"epoch": 1781517600}


def test_now_time_service_reports_current_time() -> None:
    response = httpx.get(f"{NOW_TIME_SERVICE_URL}/now")
    assert response.status_code == 200
    value = response.json()["now"]
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert abs(parsed.timestamp() - time.time()) < CLOCK_TOLERANCE_SECONDS


def test_service_to_service_communication() -> None:
    """now-time-service (B) fetches the current time and asks epoch-service (A)
    to convert it, over the Compose network — proving the two services talk."""
    response = httpx.get(f"{NOW_TIME_SERVICE_URL}/now-epoch")
    assert response.status_code == 200
    body = response.json()
    assert abs(body["epoch"] - time.time()) < CLOCK_TOLERANCE_SECONDS


def test_now_epoch_is_consistent_with_its_own_timestamp() -> None:
    """The epoch B returns must match the timestamp B reports in the same call."""
    body = httpx.get(f"{NOW_TIME_SERVICE_URL}/now-epoch").json()
    expected = datetime.fromisoformat(body["now"].replace("Z", "+00:00"))
    assert body["epoch"] == int(expected.timestamp())


def test_now_honours_timezone_override() -> None:
    """The tz query parameter changes the reported offset; the underlying
    instant (and therefore the epoch) is unchanged."""
    utc = httpx.get(f"{NOW_TIME_SERVICE_URL}/now").json()["now"]
    tokyo = httpx.get(f"{NOW_TIME_SERVICE_URL}/now", params={"tz": "Asia/Tokyo"}).json()["now"]
    assert utc.endswith("Z")
    assert tokyo.endswith("+09:00")  # Tokyo has no DST


def test_unknown_timezone_returns_400() -> None:
    response = httpx.get(f"{NOW_TIME_SERVICE_URL}/now", params={"tz": "Not/AZone"})
    assert response.status_code == 400
    assert "timezone" in response.json()["error"].lower()
