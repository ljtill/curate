"""Fetch agent — retrieves and parses submitted link content."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Annotated

import httpx
from agent_framework import Agent, ChatOptions, tool

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
from agent_stack.models.link import Link, LinkStatus

if TYPE_CHECKING:
    from agent_framework.azure import AzureOpenAIChatClient

    from agent_stack.database.repositories.links import LinkRepository

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
        """Initialize the fetch agent with LLM client and link repository."""
        self._links_repo = links_repo
        middleware = [
            TokenTrackingMiddleware(),
            *([] if rate_limiter is None else [rate_limiter]),
        ]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("fetch"),
            name="fetch-agent",
            description="Retrieves and parses submitted link content from URLs.",
            tools=[self.fetch_url, self.save_fetched_content, self.mark_link_failed],
            default_options=ChatOptions(temperature=0.0),
            middleware=middleware,
        )

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

    @staticmethod
    @tool
    async def fetch_url(url: Annotated[str, "The URL to fetch content from"]) -> str:
        """Fetch the raw HTML content of a URL."""
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; AgentStack/1.0; +https://github.com/ljtill/agent-stack)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=30.0, headers=headers
            ) as http:
                response = await http.get(url)
                response.raise_for_status()
                return response.text
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as exc:
            return json.dumps(
                {"error": f"URL is unreachable: {exc}", "unreachable": True}
            )
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {
                    "error": f"HTTP {exc.response.status_code}: {exc}",
                    "unreachable": True,
                }
            )
        except httpx.HTTPError as exc:
            return json.dumps(
                {"error": f"Failed to fetch URL: {exc}", "unreachable": True}
            )

    @tool
    async def save_fetched_content(
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

    @tool
    async def mark_link_failed(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
        reason: Annotated[str, "Why the link failed (e.g. unreachable, timeout)"],
    ) -> str:
        """Mark a link as failed when the URL is unreachable or cannot be processed."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            return json.dumps({"error": "Link not found"})
        link.status = LinkStatus.FAILED
        await self._links_repo.update(link, edition_id)
        return json.dumps({"status": "failed", "link_id": link_id, "reason": reason})

    async def run(self, link: Link) -> dict:
        """Execute the fetch agent for a given link."""
        logger.info("Fetch agent started — link=%s url=%s", link.id, link.url)
        t0 = time.monotonic()
        message = (
            f"Fetch and extract the content from this URL: {link.url}\n"
            f"Link ID: {link.id}\nEdition ID: {link.edition_id}"
        )
        try:
            response = await self._agent.run(message)
        except Exception:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.exception(
                "Fetch agent failed — link=%s duration_ms=%.0f", link.id, elapsed_ms
            )
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Fetch agent completed — link=%s duration_ms=%.0f", link.id, elapsed_ms
        )
        return {
            "usage": dict(response.usage_details)
            if response and response.usage_details
            else None,
            "message": message,
            "response": response.text if response else None,
        }
