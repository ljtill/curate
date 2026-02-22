"""Draft agent — composes or revises newsletter content from reviewed material."""

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

    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.database.repositories.links import LinkRepository

logger = logging.getLogger(__name__)


class DraftAgent:
    """Drafts newsletter content by integrating reviewed links into the edition."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        links_repo: LinkRepository,
        editions_repo: EditionRepository,
        *,
        rate_limiter: RateLimitMiddleware | None = None,
    ) -> None:
        """Initialize the draft agent with LLM client and repositories."""
        self._links_repo = links_repo
        self._editions_repo = editions_repo
        middleware = [
            TokenTrackingMiddleware(),
            *([] if rate_limiter is None else [rate_limiter]),
        ]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("draft"),
            name="draft-agent",
            description=(
                "Composes or revises newsletter content from reviewed material."
            ),
            tools=[self.get_reviewed_link, self.get_edition_content, self.save_draft],
            middleware=middleware,
        )

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

    @tool
    async def get_reviewed_link(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
    ) -> str:
        """Read the reviewed link with its review output."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            logger.warning("get_reviewed_link: link %s not found", link_id)
            return json.dumps({"error": "Link not found"})
        logger.debug("Retrieved reviewed link — link=%s", link_id)
        return json.dumps(
            {
                "title": link.title,
                "url": link.url,
                "content": link.content,
                "review": link.review,
            }
        )

    @tool
    async def get_edition_content(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Read the current edition content."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            logger.warning("get_edition_content: edition %s not found", edition_id)
            return json.dumps({"error": "Edition not found"})
        logger.debug("Retrieved edition content — edition=%s", edition_id)
        return json.dumps(edition.content)

    @tool
    async def save_draft(
        self,
        edition_id: Annotated[str, "The edition document ID"],
        link_id: Annotated[str, "The link being drafted"],
        content: Annotated[str, "Updated edition content as JSON"],
    ) -> str:
        """Update the edition content with drafted material."""
        try:
            parsed_content = (
                json.loads(content) if isinstance(content, str) else content
            )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "save_draft: invalid content JSON for edition %s: %s",
                edition_id,
                exc,
            )
            return json.dumps({"error": f"content must be valid JSON: {exc}"})
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            logger.warning("save_draft: edition %s not found", edition_id)
            return json.dumps({"error": "Edition not found"})
        edition.content = parsed_content
        if link_id not in edition.link_ids:
            edition.link_ids.append(link_id)
        await self._editions_repo.update(edition, edition_id)

        # Transition link status
        link = await self._links_repo.get(link_id, edition_id)
        if link:
            link.status = LinkStatus.DRAFTED
            await self._links_repo.update(link, edition_id)

        logger.debug(
            "Draft saved — edition=%s link=%s status=drafted",
            edition_id,
            link_id,
        )
        return json.dumps({"status": "drafted", "edition_id": edition_id})

    async def run(self, link: Link) -> dict:
        """Execute the draft agent for a reviewed link."""
        logger.debug(
            "Draft agent started — link=%s edition=%s", link.id, link.edition_id
        )
        t0 = time.monotonic()
        message = (
            f"Draft newsletter content for this reviewed link.\n"
            f"Link ID: {link.id}\nEdition ID: {link.edition_id}"
        )
        try:
            response = await self._agent.run(message)
        except Exception:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.exception(
                "Draft agent failed — link=%s edition=%s duration_ms=%.0f",
                link.id,
                link.edition_id,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.debug(
            "Draft agent completed — link=%s edition=%s duration_ms=%.0f",
            link.id,
            link.edition_id,
            elapsed_ms,
        )
        return {
            "usage": dict(response.usage_details)
            if response and response.usage_details
            else None,
            "message": message,
            "response": response.text if response else None,
        }
