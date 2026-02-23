"""Chat and function middleware for token tracking and tool logging."""

from __future__ import annotations

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
            "LLM call completed — input_tokens=%d output_tokens=%d "
            "total_tokens=%d latency_ms=%.0f",
            input_tokens,
            output_tokens,
            total_tokens,
            elapsed_ms,
        )

        meta = cast("dict[str, Any]", context.metadata)
        meta["usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "latency_ms": round(elapsed_ms),
        }


class ToolLoggingMiddleware(FunctionMiddleware):
    """Logs tool invocations on the orchestrator agent."""

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Log tool name and arguments before/after invocation."""
        name = context.function.name if context.function else "unknown"
        logger.debug("Tool invocation: %s args=%s", name, context.arguments)
        start = time.monotonic()
        await call_next()
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.debug(
            "Tool completed: %s duration_ms=%.0f result_length=%d",
            name,
            elapsed_ms,
            len(str(context.result)) if context.result else 0,
        )
