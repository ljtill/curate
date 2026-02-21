"""Pipeline orchestrator — an Agent that coordinates the editorial pipeline."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING, Annotated, Any

from agent_framework import Agent, ChatOptions, tool

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
    ) -> None:
        """Initialize the orchestrator with LLM client and all repositories."""
        self._client = client
        self._links_repo = links_repo
        self._editions_repo = editions_repo
        self._feedback_repo = feedback_repo
        self._agent_runs_repo = agent_runs_repo

        self._events = EventManager.get_instance()

        rate_limiter = RateLimitMiddleware(
            tpm_limit=int(os.environ.get("OPENAI_TPM_LIMIT", "800000")),
            rpm_limit=int(os.environ.get("OPENAI_RPM_LIMIT", "8000")),
        )

        self.fetch = FetchAgent(client, links_repo, rate_limiter=rate_limiter)
        self.review = ReviewAgent(client, links_repo, rate_limiter=rate_limiter)
        self.draft = DraftAgent(
            client, links_repo, editions_repo, rate_limiter=rate_limiter
        )
        self.edit = EditAgent(
            client, editions_repo, feedback_repo, rate_limiter=rate_limiter
        )
        self.publish = PublishAgent(
            client,
            editions_repo,
            render_fn=render_fn,
            upload_fn=upload_fn,
            rate_limiter=rate_limiter,
        )

        # Build the orchestrator agent with sub-agents as tools + custom tools
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
                # Sub-agents via as_tool()
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
                self.draft.agent.as_tool(
                    name="draft",
                    description="Compose newsletter content from reviewed material",
                    arg_name="task",
                    arg_description="Instructions including the link ID and edition ID",
                ),
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
                # Custom tools for state inspection and run tracking
                self.get_link_status,
                self.get_edition_status,
                self.record_stage_start,
                self.record_stage_complete,
            ],
            default_options=ChatOptions(temperature=0.0),
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

    # -- Custom tools for state inspection and run tracking --

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

        # Publish link-update for real-time UI
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

    # -- Event handlers --

    async def handle_link_change(self, document: dict[str, Any]) -> None:
        """Process a link document change by invoking the orchestrator agent."""
        link_id = document.get("id", "")
        edition_id = document.get("edition_id", "")
        status = document.get("status", "")

        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            logger.warning("Link %s not found, skipping", link_id)
            return

        # Skip failed links — user must click Retry to reprocess
        if link.status == LinkStatus.FAILED:
            logger.debug("Link %s is failed, skipping (use Retry)", link_id)
            return

        # Only process links with actionable statuses
        if status not in (
            LinkStatus.SUBMITTED,
            LinkStatus.FETCHING,
            LinkStatus.REVIEWED,
        ):
            logger.debug("No action needed for link %s with status %s", link_id, status)
            return

        # Skip stale/replayed events — the link has already advanced past this status
        if link.status != status:
            logger.debug(
                "Link %s already at status %s, skipping stale event (feed status: %s)",
                link_id,
                link.status,
                status,
            )
            return

        logger.info("Orchestrator processing link=%s status=%s", link_id, status)
        run = await self._create_orchestrator_run(link_id, {"status": status})
        t0 = time.monotonic()
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
        except Exception:
            logger.exception("Orchestrator failed for link %s", link_id)
            run.status = AgentRunStatus.FAILED
            run.output = {"error": "Orchestrator failed"}
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, link_id)
            await self._publish_run_event(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Orchestrator completed link=%s duration_ms=%.0f",
                link_id,
                elapsed_ms,
            )

        # If the link hasn't advanced past its original status, mark it
        # as failed so the change feed doesn't retry indefinitely.
        # The user can click Retry in the UI to try again.
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

        if document.get("resolved", False):
            return

        logger.info(
            "Orchestrator processing feedback=%s edition=%s",
            feedback_id,
            edition_id,
        )
        run = await self._create_orchestrator_run(
            feedback_id, {"edition_id": edition_id}
        )
        t0 = time.monotonic()
        try:
            message = (
                f"Editor feedback has been submitted and needs processing.\n"
                f"Edition ID: {edition_id}\n"
                f"Feedback ID: {feedback_id}\n"
                f"Run the edit stage to address the feedback."
            )
            response = await self._agent.run(message)
            run.status = AgentRunStatus.COMPLETED
            run.output = {"content": response.text if response else None}
        except Exception:
            logger.exception("Orchestrator failed for feedback %s", feedback_id)
            run.status = AgentRunStatus.FAILED
            run.output = {"error": "Orchestrator failed"}
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, feedback_id)
            await self._publish_run_event(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Orchestrator completed feedback=%s duration_ms=%.0f",
                feedback_id,
                elapsed_ms,
            )

    async def handle_publish(self, edition_id: str) -> None:
        """Process a publish approval by invoking the orchestrator agent."""
        logger.info("Orchestrator processing publish for edition=%s", edition_id)
        run = await self._create_orchestrator_run(
            edition_id, {"edition_id": edition_id}
        )
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
        except Exception:
            logger.exception("Orchestrator failed for publish edition=%s", edition_id)
            run.status = AgentRunStatus.FAILED
            run.output = {"error": "Orchestrator failed"}
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, edition_id)
            await self._publish_run_event(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Orchestrator completed publish edition=%s duration_ms=%.0f",
                edition_id,
                elapsed_ms,
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
