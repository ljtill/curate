"""Publish agent — renders HTML and uploads static files."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from agent_framework import Agent, ChatOptions, tool

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
from agent_stack.models.edition import EditionStatus

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_framework.azure import AzureOpenAIChatClient

    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.models.edition import Edition

logger = logging.getLogger(__name__)


class PublishAgent:
    """Renders the edition against the newsletter template and deploys static files."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        editions_repo: EditionRepository,
        render_fn: Callable[[Edition], Awaitable[str]] | None = None,
        upload_fn: Callable[[str, str], Awaitable[None]] | None = None,
        *,
        rate_limiter: RateLimitMiddleware | None = None,
    ) -> None:
        """Initialize the publish agent with LLM client and rendering hooks."""
        self._editions_repo = editions_repo
        self._render_fn = render_fn
        self._upload_fn = upload_fn
        middleware = [
            TokenTrackingMiddleware(),
            *([] if rate_limiter is None else [rate_limiter]),
        ]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("publish"),
            name="publish-agent",
            description=(
                "Renders final HTML against the newsletter "
                "template and deploys static pages."
            ),
            tools=[self.render_and_upload, self.mark_published],
            default_options=ChatOptions(max_tokens=500, temperature=0.0),
            middleware=middleware,
        )

    @property
    def render_fn(self) -> Callable[[Edition], Awaitable[str]] | None:
        """Return the render function."""
        return self._render_fn

    @property
    def upload_fn(self) -> Callable[[str, str], Awaitable[None]] | None:
        """Return the upload function."""
        return self._upload_fn

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

    @tool
    async def render_and_upload(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Render the edition to HTML and upload to storage."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            return json.dumps({"error": "Edition not found"})

        if self._render_fn and self._upload_fn:
            html = await self._render_fn(edition)
            await self._upload_fn(edition_id, html)
            return json.dumps({"status": "uploaded", "edition_id": edition_id})

        return json.dumps(
            {"status": "skipped", "reason": "render/upload functions not configured"}
        )

    @tool
    async def mark_published(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Mark the edition as published."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            return json.dumps({"error": "Edition not found"})
        edition.status = EditionStatus.PUBLISHED
        edition.published_at = datetime.now(UTC)
        await self._editions_repo.update(edition, edition_id)
        return json.dumps({"status": "published", "edition_id": edition_id})

    async def run(self, edition_id: str) -> dict:
        """Execute the publish agent for an edition."""
        logger.info("Publish agent started — edition=%s", edition_id)
        t0 = time.monotonic()
        message = f"Render and publish the edition.\nEdition ID: {edition_id}"
        try:
            response = await self._agent.run(message)
        except Exception:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.exception(
                "Publish agent failed — edition=%s duration_ms=%.0f",
                edition_id,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Publish agent completed — edition=%s duration_ms=%.0f",
            edition_id,
            elapsed_ms,
        )
        return {
            "usage": dict(response.usage_details)
            if response and response.usage_details
            else None,
            "message": message,
            "response": response.text if response else None,
        }
