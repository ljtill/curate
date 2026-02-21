"""Publish agent — renders HTML and uploads static files."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

from agent_framework import Agent, ChatOptions, tool
from agent_framework.azure import AzureOpenAIChatClient

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.models.edition import EditionStatus

logger = logging.getLogger(__name__)


class PublishAgent:
    """Renders the edition against the newsletter template and deploys static files."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        editions_repo: EditionRepository,
        render_fn=None,
        upload_fn=None,
        *,
        rate_limiter: RateLimitMiddleware | None = None,
    ) -> None:
        self._editions_repo = editions_repo
        self._render_fn = render_fn
        self._upload_fn = upload_fn
        middleware = [TokenTrackingMiddleware(), *([] if rate_limiter is None else [rate_limiter])]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("publish"),
            name="publish-agent",
            tools=[self._render_and_upload, self._mark_published],
            default_options=ChatOptions(max_tokens=500, temperature=0.0),
            middleware=middleware,
        )

    @tool
    async def _render_and_upload(
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

        return json.dumps({"status": "skipped", "reason": "render/upload functions not configured"})

    @tool
    async def _mark_published(
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
        logger.info("Publish agent processing edition %s", edition_id)
        message = f"Render and publish the edition.\nEdition ID: {edition_id}"
        response = await self._agent.run(message)
        return {
            "usage": dict(response.usage_details) if response and response.usage_details else None,
            "message": message,
            "response": response.text if response else None,
        }
