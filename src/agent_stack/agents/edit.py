"""Edit agent — refines tone, structure, and coherence; processes editor feedback."""

from __future__ import annotations

import json
import logging
from typing import Annotated

from agent_framework import Agent, ChatOptions, tool
from agent_framework.azure import AzureOpenAIChatClient

from agent_stack.agents.middleware import RateLimitMiddleware, TokenTrackingMiddleware
from agent_stack.agents.prompts import load_prompt
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
    ) -> None:
        self._editions_repo = editions_repo
        self._feedback_repo = feedback_repo
        middleware = [TokenTrackingMiddleware(), *([] if rate_limiter is None else [rate_limiter])]
        self._agent = Agent(
            client=client,
            instructions=load_prompt("edit"),
            name="edit-agent",
            tools=[self._get_edition_content, self._get_feedback, self._save_edit, self._resolve_feedback],
            default_options=ChatOptions(max_tokens=4000, temperature=0.5),
            middleware=middleware,
        )

    @tool
    async def _get_edition_content(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Read the current edition content."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            return json.dumps({"error": "Edition not found"})
        return json.dumps(edition.content)

    @tool
    async def _get_feedback(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Read unresolved editor feedback for the edition."""
        items = await self._feedback_repo.get_unresolved(edition_id)
        return json.dumps([{"id": f.id, "section": f.section, "comment": f.comment} for f in items])

    @tool
    async def _save_edit(
        self,
        edition_id: Annotated[str, "The edition document ID"],
        content: Annotated[str, "Updated edition content as JSON"],
    ) -> str:
        """Update the edition with refined content."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            return json.dumps({"error": "Edition not found"})
        edition.content = json.loads(content) if isinstance(content, str) else content
        await self._editions_repo.update(edition, edition_id)
        return json.dumps({"status": "edited", "edition_id": edition_id})

    @tool
    async def _resolve_feedback(
        self,
        feedback_id: Annotated[str, "The feedback document ID"],
        edition_id: Annotated[str, "The edition partition key"],
    ) -> str:
        """Mark a feedback item as resolved."""
        feedback = await self._feedback_repo.get(feedback_id, edition_id)
        if not feedback:
            return json.dumps({"error": "Feedback not found"})
        feedback.resolved = True
        await self._feedback_repo.update(feedback, edition_id)
        return json.dumps({"status": "resolved", "feedback_id": feedback_id})

    async def run(self, edition_id: str) -> dict:
        """Execute the edit agent for an edition."""
        logger.info("Edit agent processing edition %s", edition_id)
        message = f"Edit and refine the current edition. Address any unresolved feedback.\nEdition ID: {edition_id}"
        response = await self._agent.run(message)
        return {
            "usage": dict(response.usage_details) if response and response.usage_details else None,
            "message": message,
            "response": response.text if response else None,
        }
