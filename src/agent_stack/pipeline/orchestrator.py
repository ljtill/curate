"""Pipeline orchestrator — an Agent that coordinates the editorial pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING, Annotated, Any

from agent_framework import Agent, tool

from agent_stack.agents.draft import DraftAgent
from agent_stack.agents.edit import EditAgent
from agent_stack.agents.fetch import FetchAgent
from agent_stack.agents.middleware import (
    RateLimitMiddleware,
    TokenTrackingMiddleware,
    ToolLoggingMiddleware,
)
from agent_stack.agents.prompts import load_prompt
from agent_stack.agents.publish import PublishAgent
from agent_stack.agents.review import ReviewAgent
from agent_stack.events import EventManager
from agent_stack.models.agent_run import AgentRun, AgentRunStatus, AgentStage
from agent_stack.models.link import LinkStatus

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from agent_framework.azure import AzureOpenAIChatClient

    from agent_stack.database.repositories.agent_runs import AgentRunRepository
    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.database.repositories.feedback import FeedbackRepository
    from agent_stack.database.repositories.links import LinkRepository
    from agent_stack.models.edition import Edition
    from agent_stack.models.link import Link

logger = logging.getLogger(__name__)

_DISPLAY_URL_MAX_LENGTH = 50
_MAX_STAGE_RETRIES = 3
_RETRY_BASE_DELAY = 2.0


def _render_link_row(link: Link, runs: list) -> str:
    """Render an HTML table row for a link (used in SSE updates)."""
    url = escape(link.url)
    display_url = (
        (escape(link.url[:47]) + "...")
        if len(link.url) > _DISPLAY_URL_MAX_LENGTH
        else url
    )
    title = escape(link.title) if link.title else "—"
    status = escape(link.status)
    created = link.created_at.strftime("%Y-%m-%d %H:%M") if link.created_at else "—"

    if runs:
        latest = runs[-1] if runs[-1].started_at else runs[0]
        run_status = escape(latest.status)
        run_stage = escape(latest.stage)
        count = len(runs)
        suffix = "s" if count != 1 else ""
        progress = (
            f'<span class="agent-indicator">'
            f'<span class="agent-indicator-dot'
            f' agent-indicator-dot-{run_status}"></span>'
            f'<span class="stage-{run_stage}">{run_stage}</span>'
            f"</span> ({count} run{suffix})"
        )
    else:
        progress = (
            '<span class="agent-indicator" style="color: var(--text-muted);">—</span>'
        )

    return (
        f'<tr id="link-{escape(link.id)}" hx-swap-oob="true">'
        f'<td><a href="{url}" target="_blank"'
        f' style="color: var(--accent);">'
        f"{display_url}</a></td>"
        f"<td>{title}</td>"
        f'<td><span class="badge badge-{status}">{status}</span></td>'
        f"<td>{progress}</td>"
        f'<td style="color: var(--text-muted);">{created}</td>'
        f"</tr>"
    )


class PipelineOrchestrator:
    """An Agent that coordinates the editorial pipeline via sub-agent tools."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
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

        self._processing_links: set[str] = set()
        self._link_lock = asyncio.Lock()
        self._edition_locks: dict[str, asyncio.Lock] = {}
        self._edition_locks_guard = asyncio.Lock()

        rate_limiter = RateLimitMiddleware(
            tpm_limit=int(os.environ.get("OPENAI_TPM_LIMIT", "800000")),
            rpm_limit=int(os.environ.get("OPENAI_RPM_LIMIT", "8000")),
        )

        self.fetch = FetchAgent(client, links_repo, rate_limiter=rate_limiter)
        self.review = ReviewAgent(client, links_repo, rate_limiter=rate_limiter)
        self.draft = DraftAgent(
            client,
            links_repo,
            editions_repo,
            rate_limiter=rate_limiter,
            context_providers=context_providers,
        )
        self.edit = EditAgent(
            client,
            editions_repo,
            feedback_repo,
            rate_limiter=rate_limiter,
            context_providers=context_providers,
        )
        self.publish = PublishAgent(
            client,
            editions_repo,
            render_fn=render_fn,
            upload_fn=upload_fn,
            rate_limiter=rate_limiter,
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
                rate_limiter,
                ToolLoggingMiddleware(),
            ],
        )

    @property
    def agent(self) -> Agent:
        """Return the inner Agent framework instance."""
        return self._agent  # ty: ignore[invalid-return-type]

    @tool(name="draft")
    async def _draft_tool(
        self,
        task: Annotated[str, "Instructions including the link ID and edition ID"],
    ) -> str:
        """Compose newsletter content from reviewed material."""
        return await self.draft.run_with_guardrail(task)

    @tool
    async def get_link_status(
        self,
        link_id: Annotated[str, "The link document ID"],
        edition_id: Annotated[str, "The edition partition key"],
    ) -> str:
        """Get the current status and metadata of a link."""
        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            return json.dumps({"error": "Link not found"})
        return json.dumps(
            {
                "id": link.id,
                "url": link.url,
                "title": link.title,
                "status": link.status,
                "has_content": link.content is not None,
                "has_review": link.review is not None,
                "edition_id": link.edition_id,
            }
        )

    @tool
    async def get_edition_status(
        self,
        edition_id: Annotated[str, "The edition document ID"],
    ) -> str:
        """Get the current status of an edition."""
        edition = await self._editions_repo.get(edition_id, edition_id)
        if not edition:
            return json.dumps({"error": "Edition not found"})
        return json.dumps(
            {
                "id": edition.id,
                "status": edition.status,
                "link_count": len(edition.link_ids),
                "has_content": bool(edition.content),
            }
        )

    @tool
    async def record_stage_start(
        self,
        stage: Annotated[str, "Pipeline stage: fetch, review, draft, edit, or publish"],
        trigger_id: Annotated[str, "ID of the document that triggered this run"],
    ) -> str:
        """Record the start of a pipeline stage. Call before invoking a sub-agent."""
        run = AgentRun(
            stage=AgentStage(stage),
            trigger_id=trigger_id,
            input={"stage": stage},
            started_at=datetime.now(UTC),
        )
        await self._agent_runs_repo.create(run)
        await self._events.publish(
            "agent-run-start",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
            },
        )
        return json.dumps({"run_id": run.id, "stage": stage, "status": "running"})

    @tool
    async def record_stage_complete(
        self,
        run_id: Annotated[str, "The run ID returned by record_stage_start"],
        trigger_id: Annotated[str, "ID of the document that triggered this run"],
        status: Annotated[str, "Completion status: completed or failed"],
        error: Annotated[str, "Error message if failed, empty if completed"] = "",
        input_tokens: Annotated[int, "Input tokens consumed by this stage"] = 0,
        output_tokens: Annotated[int, "Output tokens consumed by this stage"] = 0,
        total_tokens: Annotated[int, "Total tokens consumed by this stage"] = 0,
    ) -> str:
        """Record the completion of a pipeline stage."""
        run = await self._agent_runs_repo.get(run_id, trigger_id)
        if not run:
            return json.dumps({"error": "Run not found"})
        run.status = (
            AgentRunStatus.COMPLETED if status == "completed" else AgentRunStatus.FAILED
        )
        run.completed_at = datetime.now(UTC)
        if error:
            run.output = {"error": error}
        if input_tokens or output_tokens or total_tokens:
            run.usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens or input_tokens + output_tokens,
            }
        await self._agent_runs_repo.update(run, trigger_id)
        await self._events.publish(
            "agent-run-complete",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "output": run.output,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat()
                if run.completed_at
                else None,
            },
        )

        link = await self._links_repo.get(trigger_id, "")
        if link:
            runs = await self._agent_runs_repo.get_by_trigger(trigger_id)
            await self._events.publish("link-update", _render_link_row(link, runs))

        return json.dumps(
            {
                "run_id": run_id,
                "status": status,
                "completed": True,
            }
        )

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
        run = await self._create_orchestrator_run(link_id, {"status": status})
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
                run.usage = self._normalize_usage(
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
        await self._publish_run_event(run)
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
                _render_link_row(updated_link, runs),
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
            run = await self._create_orchestrator_run(
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
                run.usage = self._normalize_usage(
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
                await self._publish_run_event(run)
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
        run = await self._create_orchestrator_run(
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
            run.usage = self._normalize_usage(
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
            await self._publish_run_event(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Orchestrator completed publish edition=%s duration_ms=%.0f"
                " pipeline_run_id=%s",
                edition_id,
                elapsed_ms,
                pipeline_run_id,
            )

    async def _create_orchestrator_run(
        self, trigger_id: str, input_data: dict
    ) -> AgentRun:
        """Create an agent run record for the orchestrator itself."""
        run = AgentRun(
            stage=AgentStage.ORCHESTRATOR,
            trigger_id=trigger_id,
            input=input_data,
            started_at=datetime.now(UTC),
        )
        await self._agent_runs_repo.create(run)
        await self._events.publish(
            "agent-run-start",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "started_at": (run.started_at.isoformat() if run.started_at else None),
            },
        )
        return run

    async def _publish_run_event(self, run: AgentRun) -> None:
        """Publish an SSE event when a run completes or fails."""
        await self._events.publish(
            "agent-run-complete",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "output": run.output,
                "started_at": (run.started_at.isoformat() if run.started_at else None),
                "completed_at": (
                    run.completed_at.isoformat() if run.completed_at else None
                ),
            },
        )

    @staticmethod
    def _normalize_usage(usage: dict | None) -> dict | None:
        """Normalize framework usage_details to a consistent schema."""
        if not usage:
            return None
        input_tokens = usage.get("input_token_count", 0) or 0
        output_tokens = usage.get("output_token_count", 0) or 0
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": usage.get("total_token_count", 0)
            or input_tokens + output_tokens,
        }
