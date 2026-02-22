"""Review agent — evaluates relevance, extracts insights, categorizes content."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Annotated

from agent_framework import Agent, tool

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
from agent_stack.models.link import Link, LinkStatus

if TYPE_CHECKING:
    from agent_framework.azure import AzureOpenAIChatClient

    from agent_stack.database.repositories.links import LinkRepository

logger = logging.getLogger(__name__)


MAX_SAVE_RETRIES = 3


class ReviewAgent:
    """Evaluates fetched content and writes a structured review."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        links_repo: LinkRepository,
        *,
        rate_limiter: RateLimitMiddleware | None = None,
    ) -> None:
        """Initialize the review agent with LLM client and link repository."""
        self._links_repo = links_repo
        self.save_failures = 0
        middleware = [
            TokenTrackingMiddleware(),
            *([] if rate_limiter is None else [rate_limiter]),
        ]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("review"),
            name="review-agent",
            description=(
                "Evaluates relevance, extracts key insights, and categorizes content."
            ),
            tools=[self.get_link_content, self.save_review],
            middleware=middleware,
        )

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

    @tool
    async def get_link_content(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
    ) -> str:
        """Read the fetched content for a link."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            logger.warning("get_link_content: link %s not found", link_id)
            return json.dumps({"error": "Link not found"})
        logger.debug(
            "Retrieved link content — link=%s title=%s",
            link_id,
            (link.title or "")[:60],
        )
        return json.dumps(
            {"title": link.title, "content": link.content, "url": link.url}
        )

    @tool
    async def save_review(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
        insights: Annotated[str, "JSON array of key insights"],
        category: Annotated[str, "Content category"],
        relevance_score: Annotated[int, "Relevance score 1-10"],
        justification: Annotated[str, "Brief justification for the score"],
    ) -> str:
        """Persist the review output to the link document."""
        try:
            parsed_insights: list | str = (
                json.loads(insights) if isinstance(insights, str) else insights
            )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "save_review: invalid insights JSON for link %s: %s", link_id, exc
            )
            return json.dumps({"error": f"insights must be a valid JSON array: {exc}"})
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            logger.warning("save_review: link %s not found", link_id)
            return json.dumps({"error": "Link not found"})
        link.review = {
            "insights": parsed_insights,
            "category": category,
            "relevance_score": relevance_score,
            "justification": justification,
        }
        link.status = LinkStatus.REVIEWED
        try:
            await self._links_repo.update(link, edition_id)
        except Exception as exc:
            self.save_failures += 1
            logger.warning(
                "save_review failed for link %s (attempt %d/%d): %s",
                link_id,
                self.save_failures,
                MAX_SAVE_RETRIES,
                exc,
            )
            if self.save_failures >= MAX_SAVE_RETRIES:
                msg = (
                    f"save_review failed after "
                    f"{MAX_SAVE_RETRIES} attempts "
                    f"for link {link_id}"
                )
                raise RuntimeError(msg) from exc
            return json.dumps({"error": f"Failed to save review: {exc}"})
        logger.debug(
            "Review saved — link=%s category=%s score=%d status=%s",
            link_id,
            category,
            relevance_score,
            link.status,
        )
        return json.dumps({"status": "reviewed", "link_id": link_id})

    async def run(self, link: Link) -> dict:
        """Execute the review agent for a fetched link."""
        logger.debug("Review agent started — link=%s", link.id)
        t0 = time.monotonic()
        self.save_failures = 0
        message = (
            "Review the fetched content for this link.\n"
            f"Link ID: {link.id}\nEdition ID: {link.edition_id}"
        )
        try:
            response = await self._agent.run(message)
        except Exception:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.exception(
                "Review agent failed — link=%s duration_ms=%.0f", link.id, elapsed_ms
            )
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "Review agent completed — link=%s duration_ms=%.0f", link.id, elapsed_ms
        )
        return {
            "usage": dict(response.usage_details)
            if response and response.usage_details
            else None,
            "message": message,
            "response": response.text if response else None,
        }
