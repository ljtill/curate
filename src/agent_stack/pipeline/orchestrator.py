"""Pipeline orchestrator — routes change feed events to the appropriate agent stage."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime
from html import escape
from typing import TYPE_CHECKING, Any

from agent_stack.agents.draft import DraftAgent
from agent_stack.agents.edit import EditAgent
from agent_stack.agents.fetch import FetchAgent
from agent_stack.agents.middleware import RateLimitMiddleware
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


def _render_link_row(link: Link, runs: list) -> str:
    """Render an HTML table row for a link (used in SSE updates)."""
    url = escape(link.url)
    display_url = (escape(link.url[:47]) + "...") if len(link.url) > 50 else url
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
            f'<span class="agent-indicator-dot agent-indicator-dot-{run_status}"></span>'
            f'<span class="stage-{run_stage}">{run_stage}</span>'
            f"</span> ({count} run{suffix})"
        )
    else:
        progress = '<span class="agent-indicator" style="color: var(--text-muted);">—</span>'

    return (
        f'<tr id="link-{escape(link.id)}" hx-swap-oob="true">'
        f'<td><a href="{url}" target="_blank" style="color: var(--accent);">{display_url}</a></td>'
        f"<td>{title}</td>"
        f'<td><span class="badge badge-{status}">{status}</span></td>'
        f"<td>{progress}</td>"
        f'<td style="color: var(--text-muted);">{created}</td>'
        f"</tr>"
    )


class PipelineOrchestrator:
    """Routes incoming change events to the correct agent stage."""

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
        self.draft = DraftAgent(client, links_repo, editions_repo, rate_limiter=rate_limiter)
        self.edit = EditAgent(client, editions_repo, feedback_repo, rate_limiter=rate_limiter)
        self.publish = PublishAgent(
            client, editions_repo, render_fn=render_fn, upload_fn=upload_fn, rate_limiter=rate_limiter
        )

    async def handle_link_change(self, document: dict[str, Any]) -> None:
        """Process a link document change based on its current status."""
        link_id = document.get("id", "")
        edition_id = document.get("edition_id", "")
        status = document.get("status", "")

        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            logger.warning("Link %s not found, skipping", link_id)
            return

        stage = self.determine_stage_for_link(status)
        if not stage:
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

        run = await self._create_run(stage, link_id, {"status": status})
        t0 = time.monotonic()
        logger.info("Pipeline dispatching stage=%s trigger=%s", stage, link_id)
        try:
            result = await self._execute_link_stage(stage, link)
            run.status = AgentRunStatus.COMPLETED
            run.usage = self._normalize_usage(result.get("usage") if result else None)
            if result:
                run.input = {**(run.input or {}), "message": result.get("message")}
                run.output = {"content": result.get("response")}
        except Exception as exc:
            logger.exception("Agent stage %s failed for link %s", stage, link_id)
            run.status = AgentRunStatus.FAILED
            run.output = {"error": str(exc)}
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, link_id)
            await self._publish_run_complete(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Pipeline stage=%s trigger=%s completed status=%s duration_ms=%.0f",
                stage,
                link_id,
                run.status,
                elapsed_ms,
            )

        # Mark link as failed if the fetch stage didn't advance it
        if stage == AgentStage.FETCH:
            updated_link = await self._links_repo.get(link_id, edition_id)
            if updated_link and updated_link.status == LinkStatus.SUBMITTED:
                updated_link.status = LinkStatus.FAILED
                await self._links_repo.update(updated_link, edition_id)

        # Publish link-update so the links table refreshes in-place
        updated_link = await self._links_repo.get(link_id, edition_id)
        if updated_link:
            runs = await self._agent_runs_repo.get_by_trigger(link_id)
            await self._events.publish(
                "link-update",
                _render_link_row(updated_link, runs),
            )

    async def handle_feedback_change(self, document: dict[str, Any]) -> None:
        """Process new feedback by triggering the edit agent."""
        edition_id = document.get("edition_id", "")
        feedback_id = document.get("id", "")

        if document.get("resolved", False):
            return

        run = await self._create_run(AgentStage.EDIT, feedback_id, {"edition_id": edition_id})
        t0 = time.monotonic()
        logger.info("Pipeline dispatching stage=%s trigger=%s", AgentStage.EDIT, feedback_id)
        try:
            result = await self.edit.run(edition_id)
            run.status = AgentRunStatus.COMPLETED
            run.usage = self._normalize_usage(result.get("usage") if result else None)
            if result:
                run.input = {**(run.input or {}), "message": result.get("message")}
                run.output = {"content": result.get("response")}
        except Exception as exc:
            logger.exception("Edit agent failed for feedback %s", feedback_id)
            run.status = AgentRunStatus.FAILED
            run.output = {"error": str(exc)}
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, feedback_id)
            await self._publish_run_complete(run)
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "Pipeline stage=%s trigger=%s completed status=%s duration_ms=%.0f",
                AgentStage.EDIT,
                feedback_id,
                run.status,
                elapsed_ms,
            )

    def determine_stage_for_link(self, status: str) -> AgentStage | None:
        """Map link status to the next agent stage."""
        return {
            LinkStatus.SUBMITTED: AgentStage.FETCH,
            LinkStatus.FETCHING: AgentStage.REVIEW,
            LinkStatus.REVIEWED: AgentStage.DRAFT,
        }.get(status)

    async def _execute_link_stage(self, stage: AgentStage, link: Link) -> dict | None:
        """Dispatch to the correct agent based on stage."""
        match stage:
            case AgentStage.FETCH:
                return await self.fetch.run(link)
            case AgentStage.REVIEW:
                return await self.review.run(link)
            case AgentStage.DRAFT:
                return await self.draft.run(link)
        return None

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
            "total_tokens": usage.get("total_token_count", 0) or input_tokens + output_tokens,
        }

    async def _create_run(self, stage: AgentStage, trigger_id: str, input_data: dict) -> AgentRun:
        """Create and persist an agent run document."""
        run = AgentRun(
            stage=stage,
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
                "started_at": run.started_at.isoformat() if run.started_at else None,
            },
        )
        return run

    async def _publish_run_complete(self, run: AgentRun) -> None:
        """Publish an SSE event when an agent run completes or fails."""
        await self._events.publish(
            "agent-run-complete",
            {
                "id": run.id,
                "stage": run.stage,
                "trigger_id": run.trigger_id,
                "status": run.status,
                "output": run.output,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            },
        )
