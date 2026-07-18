from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.config import Settings
from app.main import EXAMPLE_BODY, create_app, parse_iso8601
from fastapi.testclient import TestClient

SETTINGS = Settings(
    host="127.0.0.1",
    port=8080,
    epoch_path="/epoch",
    health_path="/healthz",
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(SETTINGS))


def test_assignment_example(client: TestClient) -> None:
    response = client.post("/epoch", json={"date": "2026-06-15T10:00:00Z"})
    assert response.status_code == 200
    assert response.json() == {"epoch": 1781517600}


def test_epoch_zero(client: TestClient) -> None:
    response = client.post("/epoch", json={"date": "1970-01-01T00:00:00Z"})
    assert response.status_code == 200
    assert response.json() == {"epoch": 0}


def test_date_with_utc_offset(client: TestClient) -> None:
    # 12:00 at +02:00 is the same instant as 10:00 UTC.
    response = client.post("/epoch", json={"date": "2026-06-15T12:00:00+02:00"})
    assert response.status_code == 200
    assert response.json() == {"epoch": 1781517600}


def test_naive_date_is_treated_as_utc(client: TestClient) -> None:
    response = client.post("/epoch", json={"date": "2026-06-15T10:00:00"})
    assert response.status_code == 200
    assert response.json() == {"epoch": 1781517600}


def test_date_only_is_accepted(client: TestClient) -> None:
    response = client.post("/epoch", json={"date": "2026-06-15"})
    assert response.status_code == 200
    assert response.json() == {"epoch": 1781481600}


def test_body_works_without_content_type_header(client: TestClient) -> None:
    # Regression: a valid JSON body must be accepted even when the client does
    # not send `Content-Type: application/json`.
    response = client.post("/epoch", content=b'{"date": "2026-06-15T10:00:00Z"}')
    assert response.status_code == 200
    assert response.json() == {"epoch": 1781517600}


def test_error_body_carries_code_and_usable_example(client: TestClient) -> None:
    response = client.post("/epoch", content=b"")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == 400
    # The example is a real JSON object (not an escaped string) and actually works.
    assert body["example"] == EXAMPLE_BODY
    replay = client.post("/epoch", json=body["example"])
    assert replay.status_code == 200
    assert replay.json() == {"epoch": 1781517600}


def test_empty_body_returns_400(client: TestClient) -> None:
    response = client.post("/epoch", content=b"")
    assert response.status_code == 400
    assert "empty" in response.json()["error"]


def test_invalid_date_returns_400(client: TestClient) -> None:
    response = client.post("/epoch", json={"date": "15/06/2026"})
    assert response.status_code == 400
    assert "Invalid date" in response.json()["error"]
    assert response.json()["code"] == 400


def test_missing_date_field_returns_400(client: TestClient) -> None:
    response = client.post("/epoch", json={"when": "2026-06-15T10:00:00Z"})
    assert response.status_code == 400
    assert "date" in response.json()["error"]


def test_non_string_date_returns_400(client: TestClient) -> None:
    response = client.post("/epoch", json={"date": 1781517600})
    assert response.status_code == 400


def test_malformed_json_returns_400(client: TestClient) -> None:
    response = client.post(
        "/epoch", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert "valid JSON" in response.json()["error"]


def test_wrong_method_returns_405_with_code(client: TestClient) -> None:
    response = client.get("/epoch")
    assert response.status_code == 405
    assert response.json()["code"] == 405


def test_unknown_route_returns_404_with_code(client: TestClient) -> None:
    response = client.post("/unknown", json={})
    assert response.status_code == 404
    assert response.json()["code"] == 404


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_parse_iso8601_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_iso8601("tomorrow")


def test_parse_iso8601_z_suffix() -> None:
    parsed = parse_iso8601("2026-06-15T10:00:00Z")
    assert parsed == datetime(2026, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
