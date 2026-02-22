"""Pipeline orchestrator — an Agent that coordinates the editorial pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from agent_framework import Agent

from agent_stack.agents.draft import DraftAgent
from agent_stack.agents.edit import EditAgent
from agent_stack.agents.fetch import FetchAgent
from agent_stack.agents.middleware import (
    TokenTrackingMiddleware,
    ToolLoggingMiddleware,
)
from agent_stack.agents.prompts import load_prompt
from agent_stack.agents.publish import PublishAgent
from agent_stack.agents.review import ReviewAgent
from agent_stack.events import EventManager
from agent_stack.models.agent_run import AgentRunStatus
from agent_stack.models.link import LinkStatus
from agent_stack.pipeline.rendering import render_link_row
from agent_stack.pipeline.runs import RunManager
from agent_stack.pipeline.tools import OrchestratorToolsMixin

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_framework import BaseChatClient

    from agent_stack.database.repositories.agent_runs import AgentRunRepository
    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.database.repositories.feedback import FeedbackRepository
    from agent_stack.database.repositories.links import LinkRepository
    from agent_stack.models.edition import Edition
    from agent_stack.models.link import Link

logger = logging.getLogger(__name__)

_MAX_STAGE_RETRIES = 3
_RETRY_BASE_DELAY = 2.0


class PipelineOrchestrator(OrchestratorToolsMixin):
    """An Agent that coordinates the editorial pipeline via sub-agent tools."""

    def __init__(
        self,
        client: BaseChatClient,
        links_repo: LinkRepository,
        editions_repo: EditionRepository,
        feedback_repo: FeedbackRepository,
        agent_runs_repo: AgentRunRepository,
        render_fn: Callable[[Edition], Awaitable[str]] | None = None,
        upload_fn: Callable[[str, str], Awaitable[None]] | None = None,
        context_providers: list | None = None,
    ) -> None:
        """Initialize the orchestrator with LLM client and all repositories."""
        self._client = client
        self._links_repo = links_repo
        self._editions_repo = editions_repo
        self._feedback_repo = feedback_repo
        self._agent_runs_repo = agent_runs_repo

        self._events = EventManager.get_instance()
        self._runs = RunManager(agent_runs_repo, self._events)

        self._processing_links: set[str] = set()
        self._link_lock = asyncio.Lock()
        self._edition_locks: dict[str, asyncio.Lock] = {}
        self._edition_locks_guard = asyncio.Lock()

        self.fetch = FetchAgent(client, links_repo)
        self.review = ReviewAgent(client, links_repo)
        self.draft = DraftAgent(
            client,
            links_repo,
            editions_repo,
            context_providers=context_providers,
        )
        self.edit = EditAgent(
            client,
            editions_repo,
            feedback_repo,
            context_providers=context_providers,
        )
        self.publish = PublishAgent(
            client,
            editions_repo,
            render_fn=render_fn,
            upload_fn=upload_fn,
        )

        self._agent = Agent(
            client=client,
            instructions=load_prompt("orchestrator"),
            name="orchestrator-agent",
            description=(
                "Coordinates the editorial pipeline — routes links through "
                "fetch, review, and draft stages; handles editor feedback "
                "and gated publishing."
            ),
            tools=[
                self.fetch.agent.as_tool(
                    name="fetch",
                    description="Fetch and extract content from a submitted URL",
                    arg_name="task",
                    arg_description=(
                        "Instructions including the URL, link ID, and edition ID"
                    ),
                ),
                self.review.agent.as_tool(
                    name="review",
                    description=(
                        "Evaluate relevance, extract insights, categorize content"
                    ),
                    arg_name="task",
                    arg_description="Instructions including the link ID and edition ID",
                ),
                self._draft_tool,
                self.edit.agent.as_tool(
                    name="edit",
                    description="Refine edition content and address editor feedback",
                    arg_name="task",
                    arg_description="Instructions including the edition ID",
                ),
                self.publish.agent.as_tool(
                    name="publish",
                    description="Render HTML and upload to storage",
                    arg_name="task",
                    arg_description="Instructions including the edition ID",
                ),
                self.get_link_status,
                self.get_edition_status,
                self.record_stage_start,
                self.record_stage_complete,
            ],
            middleware=[
                TokenTrackingMiddleware(),
                ToolLoggingMiddleware(),
            ],
        )

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

    async def _get_edition_lock(self, edition_id: str) -> asyncio.Lock:
        """Get or create a per-edition lock for serializing feedback processing."""
        async with self._edition_locks_guard:
            if edition_id not in self._edition_locks:
                self._edition_locks[edition_id] = asyncio.Lock()
            return self._edition_locks[edition_id]

    async def _claim_link(
        self, link_id: str, edition_id: str, status: str
    ) -> Link | None:
        """Attempt to claim a link for processing. Returns the link or None."""
        async with self._link_lock:
            if link_id in self._processing_links:
                logger.debug("Link %s already being processed, skipping", link_id)
                return None
            link = await self._links_repo.get(link_id, edition_id)
            if not link:
                logger.warning("Link %s not found, skipping", link_id)
                return None
            if link.status == LinkStatus.FAILED:
                logger.debug("Link %s is failed, skipping (use Retry)", link_id)
                return None
            if status != LinkStatus.SUBMITTED:
                logger.debug(
                    "Link %s status %s not actionable, skipping",
                    link_id,
                    status,
                )
                return None
            if link.status != status:
                logger.debug(
                    "Link %s already at %s, skipping stale event (%s)",
                    link_id,
                    link.status,
                    status,
                )
                return None
            self._processing_links.add(link_id)
            return link

    async def handle_link_change(self, document: dict[str, Any]) -> None:
        """Process a link document change by invoking the orchestrator agent."""
        link_id = document.get("id", "")
        edition_id = document.get("edition_id", "")
        status = document.get("status", "")

        link = await self._claim_link(link_id, edition_id, status)
        if link is None:
            return

        logger.info("Orchestrator processing link=%s status=%s", link_id, status)
        run = await self._runs.create_orchestrator_run(link_id, {"status": status})
        pipeline_run_id = run.id
        t0 = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, _MAX_STAGE_RETRIES + 1):
            try:
                message = (
                    f"A link needs processing through the pipeline.\n"
                    f"Link ID: {link_id}\n"
                    f"Edition ID: {edition_id}\n"
                    f"URL: {link.url}\n"
                    f"Current status: {status}"
                )
                response = await self._agent.run(message)
                run.status = AgentRunStatus.COMPLETED
                run.output = {"content": response.text if response else None}
                run.usage = RunManager.normalize_usage(
                    dict(response.usage_details)
                    if response and response.usage_details
                    else None
                )
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < _MAX_STAGE_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Orchestrator attempt %d/%d failed for link %s, "
                        "retrying in %.1fs — pipeline_run_id=%s: %s",
                        attempt,
                        _MAX_STAGE_RETRIES,
                        link_id,
                        delay,
                        pipeline_run_id,
                        exc,
                    )
                    await asyncio.sleep(delay)

        if last_error is not None:
            logger.exception(
                "Orchestrator failed for link %s after %d attempts"
                " — pipeline_run_id=%s",
                link_id,
                _MAX_STAGE_RETRIES,
                pipeline_run_id,
                exc_info=last_error,
            )
            run.status = AgentRunStatus.FAILED
            run.output = {
                "error": (f"Orchestrator failed after {_MAX_STAGE_RETRIES} attempts"),
            }

        run.completed_at = datetime.now(UTC)
        await self._agent_runs_repo.update(run, link_id)
        await self._runs.publish_run_event(run)
        async with self._link_lock:
            self._processing_links.discard(link_id)
        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "Orchestrator completed link=%s duration_ms=%.0f pipeline_run_id=%s",
            link_id,
            elapsed_ms,
            pipeline_run_id,
        )

        updated_link = await self._links_repo.get(link_id, edition_id)
        if updated_link and updated_link.status == status:
            updated_link.status = LinkStatus.FAILED
            await self._links_repo.update(updated_link, edition_id)
            runs = await self._agent_runs_repo.get_by_trigger(link_id)
            await self._events.publish(
                "link-update",
                render_link_row(updated_link, runs),
            )

    async def handle_feedback_change(self, document: dict[str, Any]) -> None:
        """Process new feedback by invoking the orchestrator agent."""
        edition_id = document.get("edition_id", "")
        feedback_id = document.get("id", "")
        learn_from_feedback = document.get("learn_from_feedback", True)

        if document.get("resolved", False):
            return

        edition_lock = await self._get_edition_lock(edition_id)
        async with edition_lock:
            logger.info(
                "Orchestrator processing feedback=%s edition=%s",
                feedback_id,
                edition_id,
            )
            run = await self._runs.create_orchestrator_run(
                feedback_id, {"edition_id": edition_id}
            )
            pipeline_run_id = run.id
            t0 = time.monotonic()
            try:
                message = (
                    f"Editor feedback has been submitted and needs processing.\n"
                    f"Edition ID: {edition_id}\n"
                    f"Feedback ID: {feedback_id}\n"
                    f"Run the edit stage to address the feedback."
                )
                # When "Learn from this feedback" is unchecked, skip memory capture
                session = self._agent.create_session()
                if not learn_from_feedback:
                    session.state["skip_memory_capture"] = True
                response = await self._agent.run(message, session=session)
                run.status = AgentRunStatus.COMPLETED
                run.output = {"content": response.text if response else None}
                run.usage = RunManager.normalize_usage(
                    dict(response.usage_details)
                    if response and response.usage_details
                    else None
                )
            except Exception:
                logger.exception(
                    "Orchestrator failed for feedback %s — pipeline_run_id=%s",
                    feedback_id,
                    pipeline_run_id,
                )
                run.status = AgentRunStatus.FAILED
                run.output = {"error": "Orchestrator failed"}
            finally:
                run.completed_at = datetime.now(UTC)
                await self._agent_runs_repo.update(run, feedback_id)
                await self._runs.publish_run_event(run)
                elapsed_ms = (time.monotonic() - t0) * 1000
                logger.info(
                    "Orchestrator completed feedback=%s duration_ms=%.0f"
                    " pipeline_run_id=%s",
                    feedback_id,
                    elapsed_ms,
                    pipeline_run_id,
                )

    async def handle_publish(self, edition_id: str) -> None:
        """Process a publish approval by invoking the orchestrator agent."""
        logger.info("Orchestrator processing publish for edition=%s", edition_id)
        run = await self._runs.create_orchestrator_run(
            edition_id, {"edition_id": edition_id}
        )
        pipeline_run_id = run.id
        t0 = time.monotonic()
        try:
            message = (
                f"The editor has approved this edition for publishing.\n"
                f"Edition ID: {edition_id}\n"
                f"Run the publish stage to render and upload it."
            )
            response = await self._agent.run(message)
            run.status = AgentRunStatus.COMPLETED
            run.output = {"content": response.text if response else None}
            run.usage = RunManager.normalize_usage(
                dict(response.usage_details)
                if response and response.usage_details
                else None
            )
        except Exception:
            logger.exception(
                "Orchestrator failed for publish edition=%s — pipeline_run_id=%s",
                edition_id,
                pipeline_run_id,
            )
            run.status = AgentRunStatus.FAILED
            run.output = {"error": "Orchestrator failed"}
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, edition_id)
            await self._runs.publish_run_event(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Orchestrator completed publish edition=%s duration_ms=%.0f"
                " pipeline_run_id=%s",
                edition_id,
                elapsed_ms,
                pipeline_run_id,
            )
