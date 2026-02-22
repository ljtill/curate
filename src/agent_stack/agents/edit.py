"""Edit agent — refines tone, structure, and coherence; processes editor feedback."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Annotated

from agent_framework import Agent, tool

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt

if TYPE_CHECKING:
    from agent_framework.azure import AzureOpenAIChatClient

    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.database.repositories.feedback import FeedbackRepository

logger = logging.getLogger(__name__)


class EditAgent:
    """Refines edition content and addresses editor feedback."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        editions_repo: EditionRepository,
        feedback_repo: FeedbackRepository,
        *,
        rate_limiter: RateLimitMiddleware | None = None,
        context_providers: list | None = None,
    ) -> None:
        """Initialize the edit agent with LLM client and repositories."""
        self._editions_repo = editions_repo
        self._feedback_repo = feedback_repo
        middleware = [
            TokenTrackingMiddleware(),
            *([] if rate_limiter is None else [rate_limiter]),
        ]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("edit"),
            name="edit-agent",
            description=(
                "Refines tone, structure, and coherence; processes editor feedback."
            ),
            tools=[
                self.get_edition_content,
                self.get_feedback,
                self.save_edit,
                self.resolve_feedback,
            ],
            context_providers=context_providers,
            middleware=middleware,
        )

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

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
    async def get_feedback(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Read unresolved editor feedback for the edition."""
        items = await self._feedback_repo.get_unresolved(edition_id)
        logger.debug(
            "Retrieved %d unresolved feedback items — edition=%s",
            len(items),
            edition_id,
        )
        return json.dumps(
            [{"id": f.id, "section": f.section, "comment": f.comment} for f in items]
        )

    @tool
    async def save_edit(
        self,
        edition_id: Annotated[str, "The edition document ID"],
        content: Annotated[str, "Updated edition content as JSON"],
    ) -> str:
        """Update the edition with refined content."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            logger.warning("save_edit: edition %s not found", edition_id)
            return json.dumps({"error": "Edition not found"})
        try:
            edition.content = (
                json.loads(content) if isinstance(content, str) else content
            )
        except (json.JSONDecodeError, TypeError):
            logger.warning("save_edit: invalid content JSON — edition=%s", edition_id)
            return json.dumps({"error": "Invalid JSON content"})
        await self._editions_repo.update(edition, edition_id)
        logger.debug("Edit saved — edition=%s", edition_id)
        return json.dumps({"status": "edited", "edition_id": edition_id})

    @tool
    async def resolve_feedback(
        self,
        feedback_id: Annotated[str, "The feedback document ID"],
        edition_id: Annotated[str, "The edition partition key"],
    ) -> str:
        """Mark a feedback item as resolved."""
        feedback = await self._feedback_repo.get(feedback_id, edition_id)
        if not feedback:
            logger.warning("resolve_feedback: feedback %s not found", feedback_id)
            return json.dumps({"error": "Feedback not found"})
        feedback.resolved = True
        await self._feedback_repo.update(feedback, edition_id)
        logger.debug(
            "Feedback resolved — feedback=%s edition=%s",
            feedback_id,
            edition_id,
        )
        return json.dumps({"status": "resolved", "feedback_id": feedback_id})

    async def run(self, edition_id: str) -> dict:
        """Execute the edit agent for an edition."""
        logger.info("Edit agent started — edition=%s", edition_id)
        t0 = time.monotonic()
        message = (
            "Edit and refine the current edition. "
            "Address any unresolved feedback.\n"
            f"Edition ID: {edition_id}"
        )
        try:
            response = await self._agent.run(message)
        except Exception:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.exception(
                "Edit agent failed — edition=%s duration_ms=%.0f",
                edition_id,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Edit agent completed — edition=%s duration_ms=%.0f", edition_id, elapsed_ms
        )
        return {
            "usage": dict(response.usage_details)
            if response and response.usage_details
            else None,
            "message": message,
            "response": response.text if response else None,
        }
