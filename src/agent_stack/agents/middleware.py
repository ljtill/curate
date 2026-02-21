"""Chat middleware for token usage tracking and rate limiting."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from agent_framework import ChatContext, ChatMiddleware
from agent_framework._types import UsageDetails

logger = logging.getLogger(__name__)


class TokenTrackingMiddleware(ChatMiddleware):
    """Logs token usage and latency after each LLM call."""

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        start = time.monotonic()
        await call_next()
        elapsed_ms = (time.monotonic() - start) * 1000

        usage: dict[str, Any] = {}
        if context.result and hasattr(context.result, "usage_details") and context.result.usage_details:
            ud = cast(UsageDetails, context.result.usage_details)
            usage = {
                "input_token_count": ud.get("input_token_count"),
                "output_token_count": ud.get("output_token_count"),
                "total_token_count": ud.get("total_token_count"),
            }

        input_tokens = usage.get("input_token_count", 0) or 0
        output_tokens = usage.get("output_token_count", 0) or 0
        total_tokens = usage.get("total_token_count", 0) or input_tokens + output_tokens

        logger.info(
            "LLM call: input_tokens=%d output_tokens=%d total_tokens=%d latency_ms=%.0f",
            input_tokens,
            output_tokens,
            total_tokens,
            elapsed_ms,
        )

        # Stash usage on context metadata for upstream consumers
        meta = cast(dict[str, Any], context.metadata)
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
        self._tpm_limit = tpm_limit
        self._rpm_limit = rpm_limit
        self._token_window: list[tuple[float, int]] = []
        self._request_window: list[float] = []
        self._lock = asyncio.Lock()

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        await self._wait_for_capacity()
        await call_next()
        await self._record_usage(context)

    async def _wait_for_capacity(self) -> None:
        """Block until both TPM and RPM budgets have capacity."""
        while True:
            async with self._lock:
                now = time.monotonic()
                self._prune(now)

                total_tokens = sum(tokens for _, tokens in self._token_window)
                total_requests = len(self._request_window)

                if total_tokens < self._tpm_limit and total_requests < self._rpm_limit:
                    return

            # Back off briefly before retrying
            await asyncio.sleep(0.1)

    async def _record_usage(self, context: ChatContext) -> None:
        """Record actual token usage from the response."""
        tokens = 0
        if context.result and hasattr(context.result, "usage_details") and context.result.usage_details:
            ud = cast(UsageDetails, context.result.usage_details)
            tokens = ud.get("total_token_count", 0) or 0

        async with self._lock:
            now = time.monotonic()
            self._token_window.append((now, tokens))
            self._request_window.append(now)

    def _prune(self, now: float) -> None:
        """Remove entries older than 60 seconds."""
        cutoff = now - 60.0
        self._token_window = [(t, n) for t, n in self._token_window if t > cutoff]
        self._request_window = [t for t in self._request_window if t > cutoff]
