"""Tests for agent middleware — token tracking and rate limiting."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware


@pytest.mark.unit
class TestTokenTrackingMiddleware:
    @pytest.fixture
    def middleware(self):
        return TokenTrackingMiddleware()

    async def test_logs_usage_and_sets_metadata(self, middleware):
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {
            "input_token_count": 100,
            "output_token_count": 50,
            "total_token_count": 150,
        }
        context.metadata = {}

        call_next = AsyncMock()
        await middleware.process(context, call_next)

        call_next.assert_awaited_once()
        assert context.metadata["usage"]["input_tokens"] == 100
        assert context.metadata["usage"]["output_tokens"] == 50
        assert context.metadata["usage"]["total_tokens"] == 150
        assert "latency_ms" in context.metadata["usage"]

    async def test_handles_no_usage_details(self, middleware):
        context = MagicMock()
        context.result = None
        context.metadata = {}

        await middleware.process(context, AsyncMock())

        assert context.metadata["usage"]["input_tokens"] == 0
        assert context.metadata["usage"]["output_tokens"] == 0

    async def test_handles_missing_usage_fields(self, middleware):
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {}
        context.metadata = {}

        await middleware.process(context, AsyncMock())

        assert context.metadata["usage"]["input_tokens"] == 0
        assert context.metadata["usage"]["total_tokens"] == 0


@pytest.mark.unit
class TestRateLimitMiddleware:
    @pytest.fixture
    def middleware(self):
        return RateLimitMiddleware(tpm_limit=1000, rpm_limit=10)

    async def test_passes_through_when_under_limit(self, middleware):
        context = MagicMock()
        context.result = None
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_awaited_once()

    async def test_records_usage_after_call(self, middleware):
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {"total_token_count": 500}

        await middleware.process(context, AsyncMock())

        assert len(middleware._token_window) == 1
        assert len(middleware._request_window) == 1
        assert middleware._token_window[0][1] == 500

    async def test_prune_removes_old_entries(self, middleware):
        import time

        old_time = time.monotonic() - 120
        middleware._token_window = [(old_time, 500)]
        middleware._request_window = [old_time]

        middleware._prune(time.monotonic())

        assert len(middleware._token_window) == 0
        assert len(middleware._request_window) == 0

    async def test_records_zero_tokens_when_no_usage(self, middleware):
        context = MagicMock()
        context.result = None

        await middleware.process(context, AsyncMock())

        assert middleware._token_window[0][1] == 0
