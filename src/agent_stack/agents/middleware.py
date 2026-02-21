"""Chat and function middleware for token tracking, rate limiting, and tool logging."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from agent_framework import (
    ChatContext,
    ChatMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_framework._types import UsageDetails

logger = logging.getLogger(__name__)


class TokenTrackingMiddleware(ChatMiddleware):
    """Logs token usage and latency after each LLM call."""

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Track token usage and latency for an LLM call."""
        start = time.monotonic()
        await call_next()
        elapsed_ms = (time.monotonic() - start) * 1000

        usage: dict[str, Any] = {}
        if (
            context.result
            and hasattr(context.result, "usage_details")
            and context.result.usage_details
        ):
            ud = cast("UsageDetails", context.result.usage_details)
            usage = {
                "input_token_count": ud.get("input_token_count"),
                "output_token_count": ud.get("output_token_count"),
                "total_token_count": ud.get("total_token_count"),
            }

        input_tokens = usage.get("input_token_count", 0) or 0
        output_tokens = usage.get("output_token_count", 0) or 0
        total_tokens = usage.get("total_token_count", 0) or input_tokens + output_tokens

        logger.info(
            "LLM call: input_tokens=%d output_tokens=%d "
            "total_tokens=%d latency_ms=%.0f",
            input_tokens,
            output_tokens,
            total_tokens,
            elapsed_ms,
        )

        # Stash usage on context metadata for upstream consumers
        meta = cast("dict[str, Any]", context.metadata)
        meta["usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "latency_ms": round(elapsed_ms),
        }


class RateLimitMiddleware(ChatMiddleware):
    """Token-bucket rate limiter for TPM and RPM constraints.

    Defaults to 80% of Foundry GPT-5.2 limits to leave headroom.
    Override via constructor or OPENAI_TPM_LIMIT / OPENAI_RPM_LIMIT env vars.
    """

    def __init__(
        self,
        tpm_limit: int = 800_000,
        rpm_limit: int = 8_000,
    ) -> None:
        """Initialize the rate limiter with TPM and RPM constraints."""
        self._tpm_limit = tpm_limit
        self._rpm_limit = rpm_limit
        self._token_window: list[tuple[float, int]] = []
        self._request_window: list[float] = []
        self._lock = asyncio.Lock()

    @property
    def token_window(self) -> list[tuple[float, int]]:
        """Return the token usage window."""
        return self._token_window

    @token_window.setter
    def token_window(self, value: list[tuple[float, int]]) -> None:
        self._token_window = value

    @property
    def request_window(self) -> list[float]:
        """Return the request window."""
        return self._request_window

    @request_window.setter
    def request_window(self, value: list[float]) -> None:
        self._request_window = value

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Enforce rate limits before forwarding the LLM call."""
        await self._wait_for_capacity()
        await call_next()
        await self._record_usage(context)

    async def _wait_for_capacity(self) -> None:
        """Block until both TPM and RPM budgets have capacity."""
        while True:
            async with self._lock:
                now = time.monotonic()
                self.prune(now)

                total_tokens = sum(tokens for _, tokens in self._token_window)
                total_requests = len(self._request_window)

                if total_tokens < self._tpm_limit and total_requests < self._rpm_limit:
                    return

            # Back off briefly before retrying
            await asyncio.sleep(0.1)

    async def _record_usage(self, context: ChatContext) -> None:
        """Record actual token usage from the response."""
        tokens = 0
        if (
            context.result
            and hasattr(context.result, "usage_details")
            and context.result.usage_details
        ):
            ud = cast("UsageDetails", context.result.usage_details)
            tokens = ud.get("total_token_count", 0) or 0

        async with self._lock:
            now = time.monotonic()
            self._token_window.append((now, tokens))
            self._request_window.append(now)

    def prune(self, now: float) -> None:
        """Remove entries older than 60 seconds."""
        cutoff = now - 60.0
        self._token_window = [(t, n) for t, n in self._token_window if t > cutoff]
        self._request_window = [t for t in self._request_window if t > cutoff]


class ToolLoggingMiddleware(FunctionMiddleware):
    """Logs tool invocations on the orchestrator agent."""

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Log tool name and arguments before/after invocation."""
        name = context.function.name if context.function else "unknown"
        logger.info("Tool invocation: %s args=%s", name, context.arguments)
        start = time.monotonic()
        await call_next()
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "Tool completed: %s duration_ms=%.0f result_length=%d",
            name,
            elapsed_ms,
            len(str(context.result)) if context.result else 0,
        )
