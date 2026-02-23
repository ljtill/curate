"""Tests for request diagnostics middleware."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from curate_common.config import Settings
from curate_web.app import _install_request_diagnostics_middleware

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch


def _settings_with_slow_threshold(
    monkeypatch: MonkeyPatch, threshold_ms: int
) -> Settings:
    monkeypatch.setenv("APP_SLOW_REQUEST_MS", str(threshold_ms))
    return Settings()


def test_request_diagnostics_sets_request_id_header(monkeypatch: MonkeyPatch) -> None:
    """Verify middleware injects x-request-id into responses."""
    app = FastAPI()
    settings = _settings_with_slow_threshold(monkeypatch, threshold_ms=800)
    _install_request_diagnostics_middleware(app, settings)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/ping")

    assert response.headers["x-request-id"]


def test_request_diagnostics_warns_for_slow_requests(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """Verify warning logs are emitted when request exceeds threshold."""
    app = FastAPI()
    settings = _settings_with_slow_threshold(monkeypatch, threshold_ms=0)
    _install_request_diagnostics_middleware(app, settings)

    @app.get("/slow")
    async def slow() -> PlainTextResponse:
        await asyncio.sleep(0.001)
        return PlainTextResponse("ok")

    with (
        caplog.at_level(logging.WARNING, logger="curate_web.app"),
        TestClient(app) as client,
    ):
        client.get("/slow")

    assert any(
        record.levelno == logging.WARNING and "path=/slow" in record.getMessage()
        for record in caplog.records
    )


def test_request_diagnostics_does_not_warn_for_events(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    """Verify /events path is excluded from slow request warnings."""
    app = FastAPI()
    settings = _settings_with_slow_threshold(monkeypatch, threshold_ms=0)
    _install_request_diagnostics_middleware(app, settings)

    @app.get("/events")
    async def events() -> PlainTextResponse:
        await asyncio.sleep(0.001)
        return PlainTextResponse("ok")

    with (
        caplog.at_level(logging.WARNING, logger="curate_web.app"),
        TestClient(app) as client,
    ):
        client.get("/events")

    assert not caplog.records
