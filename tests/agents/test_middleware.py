"""Tests for agent middleware — token tracking and rate limiting."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware


@pytest.mark.unit
class TestTokenTrackingMiddleware:
    """Test the Token Tracking Middleware."""

    @pytest.fixture
    def middleware(self) -> TokenTrackingMiddleware:
        """Create a middleware for testing."""
        return TokenTrackingMiddleware()

    async def test_logs_usage_and_sets_metadata(self, middleware: TokenTrackingMiddleware) -> None:
        """Verify logs usage and sets metadata."""
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

    async def test_handles_no_usage_details(self, middleware: TokenTrackingMiddleware) -> None:
        """Verify handles no usage details."""
        context = MagicMock()
        context.result = None
        context.metadata = {}

        await middleware.process(context, AsyncMock())

        assert context.metadata["usage"]["input_tokens"] == 0
        assert context.metadata["usage"]["output_tokens"] == 0

    async def test_handles_missing_usage_fields(self, middleware: TokenTrackingMiddleware) -> None:
        """Verify handles missing usage fields."""
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {}
        context.metadata = {}

        await middleware.process(context, AsyncMock())

        assert context.metadata["usage"]["input_tokens"] == 0
        assert context.metadata["usage"]["total_tokens"] == 0


@pytest.mark.unit
class TestRateLimitMiddleware:
    """Test the Rate Limit Middleware."""

    @pytest.fixture
    def middleware(self) -> tuple[RateLimitMiddleware, object]:
        """Create a middleware for testing."""
        return RateLimitMiddleware(tpm_limit=1000, rpm_limit=10)

    async def test_passes_through_when_under_limit(self, middleware: RateLimitMiddleware) -> None:
        """Verify passes through when under limit."""
        context = MagicMock()
        context.result = None
        call_next = AsyncMock()

        await middleware.process(context, call_next)

        call_next.assert_awaited_once()

    async def test_records_usage_after_call(self, middleware: RateLimitMiddleware) -> None:
        """Verify records usage after call."""
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {"total_token_count": 500}

        await middleware.process(context, AsyncMock())

        assert len(middleware.token_window) == 1
        assert len(middleware.request_window) == 1
        assert middleware.token_window[0][1] == 500

    async def test_prune_removes_old_entries(self, middleware: RateLimitMiddleware) -> None:
        """Verify prune removes old entries."""
        import time

        old_time = time.monotonic() - 120
        middleware.token_window = [(old_time, 500)]
        middleware.request_window = [old_time]

        middleware.prune(time.monotonic())

        assert len(middleware.token_window) == 0
        assert len(middleware.request_window) == 0

    async def test_records_zero_tokens_when_no_usage(self, middleware: RateLimitMiddleware) -> None:
        """Verify records zero tokens when no usage."""
        context = MagicMock()
        context.result = None

        await middleware.process(context, AsyncMock())

        assert middleware.token_window[0][1] == 0
