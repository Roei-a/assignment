from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from app.config import Settings
from app.main import UnknownTimezone, create_app
from fastapi.testclient import TestClient

SETTINGS = Settings(
    host="127.0.0.1",
    port=8081,
    now_path="/now",
    now_epoch_path="/now-epoch",
    health_path="/healthz",
    epoch_service_url="http://epoch-service:8080",
    default_timezone="UTC",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SETTINGS))


def patch_epoch_service(monkeypatch, handler) -> None:
    """Replace httpx.AsyncClient with one backed by a mock transport, so the
    /now-epoch tests never need a real epoch-service running."""
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("app.main.httpx.AsyncClient", factory)


def within_tolerance(iso_value: str, seconds: int = 30) -> bool:
    parsed = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    return abs(parsed.timestamp() - datetime.now(timezone.utc).timestamp()) < seconds


def test_now_returns_current_utc_time(client: TestClient) -> None:
    before = datetime.now(timezone.utc).replace(microsecond=0)
    response = client.get("/now")
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    value = response.json()["now"]
    assert value.endswith("Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert before <= parsed <= after


def test_now_accepts_timezone_param(client: TestClient) -> None:
    response = client.get("/now", params={"tz": "Asia/Tokyo"})
    assert response.status_code == 200
    value = response.json()["now"]
    # Tokyo has no DST — always +09:00 — and is the same instant as UTC now.
    assert value.endswith("+09:00")
    assert within_tolerance(value)


def test_now_uses_configured_default_timezone() -> None:
    settings = replace(SETTINGS, default_timezone="Asia/Tokyo")
    client = TestClient(create_app(settings))
    value = client.get("/now").json()["now"]
    assert value.endswith("+09:00")


def test_now_rejects_unknown_timezone(client: TestClient) -> None:
    response = client.get("/now", params={"tz": "Mars/Phobos"})
    assert response.status_code == 400
    assert "timezone" in response.json()["error"].lower()


def test_invalid_default_timezone_fails_fast() -> None:
    settings = replace(SETTINGS, default_timezone="Nowhere/Nowhere")
    with pytest.raises(UnknownTimezone):
        create_app(settings)


def test_now_epoch_happy_path(client: TestClient, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/epoch"
        return httpx.Response(200, json={"epoch": 1781517600})

    patch_epoch_service(monkeypatch, handler)
    response = client.get("/now-epoch")
    assert response.status_code == 200
    body = response.json()
    assert body["epoch"] == 1781517600
    assert body["now"].endswith("Z")


def test_now_epoch_applies_timezone_to_reported_time(client: TestClient, monkeypatch) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["date"] = json.loads(request.content)["date"]
        return httpx.Response(200, json={"epoch": 1781517600})

    patch_epoch_service(monkeypatch, handler)
    response = client.get("/now-epoch", params={"tz": "Asia/Tokyo"})
    assert response.status_code == 200
    # Both the reported time and the date sent to Service A carry the offset.
    assert response.json()["now"].endswith("+09:00")
    assert captured["date"].endswith("+09:00")


def test_now_epoch_rejects_unknown_timezone(client: TestClient) -> None:
    response = client.get("/now-epoch", params={"tz": "Nope/Nope"})
    assert response.status_code == 400
    body = response.json()
    assert "timezone" in body["error"].lower()
    assert body["code"] == 400


def test_now_epoch_when_epoch_service_unreachable(client: TestClient, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    patch_epoch_service(monkeypatch, handler)
    response = client.get("/now-epoch")
    assert response.status_code == 502
    body = response.json()
    assert "epoch-service" in body["error"]
    assert body["code"] == 502


def test_now_epoch_when_epoch_service_errors(client: TestClient, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad date"})

    patch_epoch_service(monkeypatch, handler)
    response = client.get("/now-epoch")
    assert response.status_code == 502
    assert "unexpected status 400" in response.json()["error"]


def test_now_epoch_when_epoch_service_returns_garbage(client: TestClient, monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    patch_epoch_service(monkeypatch, handler)
    response = client.get("/now-epoch")
    assert response.status_code == 502
    assert "out of sync" in response.json()["error"]


def test_unknown_route_returns_404_with_code(client: TestClient) -> None:
    response = client.get("/unknown")
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
