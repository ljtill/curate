"""Review agent — evaluates relevance, extracts insights, categorizes content."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from agent_framework import Agent, ChatOptions, tool
from agent_framework.azure import AzureOpenAIChatClient

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.models.link import Link, LinkStatus

logger = logging.getLogger(__name__)


class ReviewAgent:
    """Evaluates fetched content and writes a structured review."""

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
            instructions=load_prompt("review"),
            name="review-agent",
            tools=[self._get_link_content, self._save_review],
            default_options=ChatOptions(max_tokens=1000, temperature=0.3),
            middleware=middleware,
        )

    @tool
    async def _get_link_content(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
    ) -> str:
        """Read the fetched content for a link."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            return json.dumps({"error": "Link not found"})
        return json.dumps({"title": link.title, "content": link.content, "url": link.url})

    @tool
    async def _save_review(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
        insights: Annotated[str, "JSON array of key insights"],
        category: Annotated[str, "Content category"],
        relevance_score: Annotated[int, "Relevance score 1-10"],
        justification: Annotated[str, "Brief justification for the score"],
    ) -> str:
        """Persist the review output to the link document."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            return json.dumps({"error": "Link not found"})
        link.review = {
            "insights": json.loads(insights) if isinstance(insights, str) else insights,
            "category": category,
            "relevance_score": relevance_score,
            "justification": justification,
        }
        link.status = LinkStatus.REVIEWED
        await self._links_repo.update(link, edition_id)
        return json.dumps({"status": "reviewed", "link_id": link_id})

    async def run(self, link: Link) -> dict:
        """Execute the review agent for a fetched link."""
        logger.info("Review agent processing link %s", link.id)
        message = f"Review the fetched content for this link.\nLink ID: {link.id}\nEdition ID: {link.edition_id}"
        response = await self._agent.run(message)
        return {
            "usage": dict(response.usage_details) if response and response.usage_details else None,
            "message": message,
            "response": response.text if response else None,
        }
