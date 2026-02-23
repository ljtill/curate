"""Tests for agent middleware — token tracking."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from curate_worker.agents.middleware import TokenTrackingMiddleware

_EXPECTED_INPUT_TOKENS = 100
_EXPECTED_OUTPUT_TOKENS = 50
_EXPECTED_TOTAL_TOKENS = 150


class TestTokenTrackingMiddleware:
    """Test the Token Tracking Middleware."""

    @pytest.fixture
    def middleware(self) -> TokenTrackingMiddleware:
        """Create a middleware for testing."""
        return TokenTrackingMiddleware()

    async def test_logs_usage_and_sets_metadata(
        self, middleware: TokenTrackingMiddleware
    ) -> None:
        """Verify logs usage and sets metadata."""
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {
            "input_token_count": _EXPECTED_INPUT_TOKENS,
            "output_token_count": _EXPECTED_OUTPUT_TOKENS,
            "total_token_count": _EXPECTED_TOTAL_TOKENS,
        }
        context.metadata = {}

        call_next = AsyncMock()
        await middleware.process(context, call_next)

        call_next.assert_awaited_once()
        assert context.metadata["usage"]["input_tokens"] == _EXPECTED_INPUT_TOKENS
        assert context.metadata["usage"]["output_tokens"] == _EXPECTED_OUTPUT_TOKENS
        assert context.metadata["usage"]["total_tokens"] == _EXPECTED_TOTAL_TOKENS
        assert "latency_ms" in context.metadata["usage"]

    async def test_handles_no_usage_details(
        self, middleware: TokenTrackingMiddleware
    ) -> None:
        """Verify handles no usage details."""
        context = MagicMock()
        context.result = None
        context.metadata = {}

        await middleware.process(context, AsyncMock())

        assert context.metadata["usage"]["input_tokens"] == 0
        assert context.metadata["usage"]["output_tokens"] == 0

    async def test_handles_missing_usage_fields(
        self, middleware: TokenTrackingMiddleware
    ) -> None:
        """Verify handles missing usage fields."""
        context = MagicMock()
        context.result = MagicMock()
        context.result.usage_details = {}
        context.metadata = {}

        await middleware.process(context, AsyncMock())

        assert context.metadata["usage"]["input_tokens"] == 0
        assert context.metadata["usage"]["total_tokens"] == 0
