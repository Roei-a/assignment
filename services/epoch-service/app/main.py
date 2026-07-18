"""Epoch service (Service A): converts ISO-8601 dates to Unix epoch timestamps.

This service is self-contained: it takes a date and returns its epoch. It has
no knowledge of, and no dependency on, any other service.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, load_settings

# A real, copy-pasteable example request body (returned as structured JSON in
# error responses, not embedded as an escaped string).
EXAMPLE_BODY = {"date": "2026-06-15T10:00:00Z"}


def parse_iso8601(value: str) -> datetime:
    """Parse an ISO-8601 date string.

    Naive datetimes (no timezone designator) are interpreted as UTC.
    """
    text = value.strip()
    # datetime.fromisoformat only accepts the "Z" suffix from Python 3.11.
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def error_response(status_code: int, message: str, example: Any = None) -> JSONResponse:
    """Uniform error body: always carries the HTTP status code, and optionally a
    copy-pasteable example request body."""
    body: dict[str, Any] = {"code": status_code, "error": message}
    if example is not None:
        body["example"] = example
    return JSONResponse(status_code=status_code, content=body)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="epoch-service")

    @app.exception_handler(StarletteHTTPException)
    async def on_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Covers framework-raised errors such as 404 (unknown route) and 405
        # (method not allowed), giving them the same {error, code} shape.
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        return error_response(500, "Internal server error.")

    @app.post(settings.epoch_path)
    async def epoch(request: Request) -> JSONResponse:
        # Parse the body ourselves so the endpoint works regardless of the
        # Content-Type header, and so every failure has a clear message.
        raw = await request.body()
        if not raw or not raw.strip():
            return error_response(
                400,
                "Request body is empty: send a JSON object with a string 'date' field.",
                example=EXAMPLE_BODY,
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return error_response(
                400,
                "Request body is not valid JSON: send a JSON object with a string 'date' field.",
                example=EXAMPLE_BODY,
            )
        if not isinstance(payload, dict) or not isinstance(payload.get("date"), str):
            return error_response(
                400,
                "Request body must be a JSON object with a string 'date' field.",
                example=EXAMPLE_BODY,
            )
        try:
            parsed = parse_iso8601(payload["date"])
        except ValueError:
            return error_response(
                400,
                f"Invalid date '{payload['date']}': expected an ISO-8601 datetime, "
                "e.g. 2026-06-15T10:00:00Z",
                example=EXAMPLE_BODY,
            )
        return JSONResponse(content={"epoch": int(parsed.timestamp())})

    @app.get(settings.health_path)
    async def health() -> JSONResponse:
        return JSONResponse(content={"status": "ok"})

    return app


def main() -> None:
    import uvicorn

    settings = load_settings()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
