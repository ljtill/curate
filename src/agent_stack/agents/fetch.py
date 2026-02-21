"""Fetch agent — retrieves and parses submitted link content."""

from __future__ import annotations

import json
import logging
from typing import Annotated

import httpx
from agent_framework import Agent, ChatOptions, tool
from agent_framework.azure import AzureOpenAIChatClient

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.models.link import Link, LinkStatus

logger = logging.getLogger(__name__)


class FetchAgent:
    """Fetches URL content and updates the link document."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        links_repo: LinkRepository,
        *,
        rate_limiter: RateLimitMiddleware | None = None,
    ) -> None:
        self._links_repo = links_repo
        middleware = [TokenTrackingMiddleware(), *([] if rate_limiter is None else [rate_limiter])]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("fetch"),
            name="fetch-agent",
            tools=[self._fetch_url, self._save_fetched_content],
            default_options=ChatOptions(max_tokens=2000, temperature=0.0),
            middleware=middleware,
        )

    @staticmethod
    @tool
    async def _fetch_url(url: Annotated[str, "The URL to fetch content from"]) -> str:
        """Fetch the raw HTML content of a URL."""
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as http:
            response = await http.get(url)
            response.raise_for_status()
            return response.text

    @tool
    async def _save_fetched_content(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
        title: Annotated[str, "Extracted page title"],
        content: Annotated[str, "Extracted main text content"],
    ) -> str:
        """Persist extracted title and content to the link document."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            return json.dumps({"error": "Link not found"})
        link.title = title
        link.content = content
        link.status = LinkStatus.FETCHING
        await self._links_repo.update(link, edition_id)
        return json.dumps({"status": "saved", "link_id": link_id})

    async def run(self, link: Link) -> dict | None:
        """Execute the fetch agent for a given link."""
        logger.info("Fetch agent processing link %s (%s)", link.id, link.url)
        message = (
            f"Fetch and extract the content from this URL: {link.url}\n"
            f"Link ID: {link.id}\nEdition ID: {link.edition_id}"
        )
        response = await self._agent.run(message)
        if response and response.usage_details:
            return dict(response.usage_details)
        return None
