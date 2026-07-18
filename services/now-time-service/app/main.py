"""now-time-service (Service B).

- GET /now        -> returns the current time in ISO-8601 format.
- GET /now-epoch  -> takes the current time, asks epoch-service (Service A) to
                     convert it, and returns the resulting Unix epoch.

Both endpoints report the time in a timezone. The default timezone comes from
the config file (time.default_timezone) and can be overridden per-request with
the `tz` query parameter, using IANA names (e.g. UTC, America/New_York).

Every error response carries both an HTTP status code and a human-readable
explanation of what most likely went wrong.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import Settings, load_settings


def format_now(zone: ZoneInfo) -> str:
    """Current time in the given zone as ISO-8601, seconds precision.

    UTC is rendered with the conventional 'Z' suffix; other zones carry their
    explicit numeric offset (e.g. '+03:00')."""
    text = datetime.now(zone).replace(microsecond=0).isoformat()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def error_response(status_code: int, message: str) -> JSONResponse:
    """Uniform error body: always carries the HTTP status code alongside the
    human-readable message."""
    return JSONResponse(status_code=status_code, content={"code": status_code, "error": message})


class UnknownTimezone(Exception):
    """Raised when a timezone name cannot be resolved."""


def resolve_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UnknownTimezone(name) from exc


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    # Fail fast if the configured default timezone is invalid.
    default_zone = resolve_zone(settings.default_timezone)
    app = FastAPI(title="now-time-service")

    @app.exception_handler(StarletteHTTPException)
    async def on_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Covers framework-raised errors such as 404 (unknown route) and 405
        # (method not allowed), giving them the same {error, code} shape.
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        return error_response(500, "Internal server error.")

    def pick_zone(tz: str | None) -> ZoneInfo:
        return resolve_zone(tz) if tz else default_zone

    def unknown_tz_error(tz: str | None) -> JSONResponse:
        return error_response(
            400,
            f"Unknown timezone '{tz}'. Expected an IANA timezone name such as "
            "'UTC', 'America/New_York', or 'Asia/Jerusalem'.",
        )

    @app.get(settings.now_path)
    async def now(tz: Optional[str] = None) -> JSONResponse:
        try:
            zone = pick_zone(tz)
        except UnknownTimezone:
            return unknown_tz_error(tz)
        return JSONResponse(content={"now": format_now(zone)})

    @app.get(settings.now_epoch_path)
    async def now_epoch(tz: Optional[str] = None) -> JSONResponse:
        """Get the current time and convert it to epoch via epoch-service."""
        try:
            zone = pick_zone(tz)
        except UnknownTimezone:
            return unknown_tz_error(tz)

        current = format_now(zone)
        url = f"{settings.epoch_service_url}/epoch"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(url, json={"date": current})
        except httpx.RequestError:
            return error_response(
                502,
                f"Could not reach epoch-service at {url}. It is probably not "
                "running or not yet ready — check that Service A is up.",
            )

        if response.status_code != 200:
            return error_response(
                502,
                f"epoch-service returned an unexpected status {response.status_code} "
                f"for date '{current}'. It probably rejected the request or hit an "
                "internal error.",
            )

        try:
            epoch = response.json()["epoch"]
        except (ValueError, KeyError):
            return error_response(
                502,
                "epoch-service responded, but the body was not the expected "
                '{"epoch": <int>} JSON. The two services may be out of sync.',
            )

        return JSONResponse(content={"now": current, "epoch": epoch})

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
