"""Pipeline orchestrator — routes change feed events to the appropriate agent stage."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from agent_framework.azure import AzureOpenAIChatClient

from agent_stack.agents.draft import DraftAgent
from agent_stack.agents.edit import EditAgent
from agent_stack.agents.fetch import FetchAgent
from agent_stack.agents.publish import PublishAgent
from agent_stack.agents.review import ReviewAgent
from agent_stack.database.repositories.agent_runs import AgentRunRepository
from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.database.repositories.feedback import FeedbackRepository
from agent_stack.database.repositories.links import LinkRepository
from agent_stack.events import EventManager
from agent_stack.models.agent_run import AgentRun, AgentRunStatus, AgentStage
from agent_stack.models.link import LinkStatus

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Routes incoming change events to the correct agent stage."""

    def __init__(
        self,
        client: AzureOpenAIChatClient,
        links_repo: LinkRepository,
        editions_repo: EditionRepository,
        feedback_repo: FeedbackRepository,
        agent_runs_repo: AgentRunRepository,
        render_fn=None,
        upload_fn=None,
    ) -> None:
        self._client = client
        self._links_repo = links_repo
        self._editions_repo = editions_repo
        self._feedback_repo = feedback_repo
        self._agent_runs_repo = agent_runs_repo

        self._events = EventManager.get_instance()

        self._fetch = FetchAgent(client, links_repo)
        self._review = ReviewAgent(client, links_repo)
        self._draft = DraftAgent(client, links_repo, editions_repo)
        self._edit = EditAgent(client, editions_repo, feedback_repo)
        self._publish = PublishAgent(client, editions_repo, render_fn=render_fn, upload_fn=upload_fn)

    async def handle_link_change(self, document: dict[str, Any]) -> None:
        """Process a link document change based on its current status."""
        link_id = document.get("id", "")
        edition_id = document.get("edition_id", "")
        status = document.get("status", "")

        link = await self._links_repo.get(link_id, edition_id)
        if not link:
            logger.warning("Link %s not found, skipping", link_id)
            return

        stage = self._determine_stage_for_link(status)
        if not stage:
            logger.debug("No action needed for link %s with status %s", link_id, status)
            return

        run = await self._create_run(stage, link_id, {"status": status})
        try:
            await self._execute_link_stage(stage, link)
            run.status = AgentRunStatus.COMPLETED
        except Exception:
            logger.exception("Agent stage %s failed for link %s", stage, link_id)
            run.status = AgentRunStatus.FAILED
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, link_id)
            await self._publish_run_complete(run)

        # Publish link-update so the links table refreshes in-place
        updated_link = await self._links_repo.get(link_id, edition_id)
        if updated_link:
            await self._events.publish(
                "link-update",
                {
                    "id": updated_link.id,
                    "url": updated_link.url,
                    "title": updated_link.title,
                    "status": updated_link.status,
                    "edition_id": updated_link.edition_id,
                },
            )

    async def handle_feedback_change(self, document: dict[str, Any]) -> None:
        """Process new feedback by triggering the edit agent."""
        edition_id = document.get("edition_id", "")
        feedback_id = document.get("id", "")

        if document.get("resolved", False):
            return

        run = await self._create_run(AgentStage.EDIT, feedback_id, {"edition_id": edition_id})
        try:
            await self._edit.run(edition_id)
            run.status = AgentRunStatus.COMPLETED
        except Exception:
            logger.exception("Edit agent failed for feedback %s", feedback_id)
            run.status = AgentRunStatus.FAILED
        finally:
            run.completed_at = datetime.now(UTC)
            await self._agent_runs_repo.update(run, feedback_id)
            await self._publish_run_complete(run)

    def _determine_stage_for_link(self, status: str) -> AgentStage | None:
        """Map link status to the next agent stage."""
        return {
            LinkStatus.SUBMITTED: AgentStage.FETCH,
            LinkStatus.FETCHING: AgentStage.REVIEW,
            LinkStatus.REVIEWED: AgentStage.DRAFT,
        }.get(status)

    async def _execute_link_stage(self, stage: AgentStage, link) -> None:
        """Dispatch to the correct agent based on stage."""
        match stage:
            case AgentStage.FETCH:
                await self._fetch.run(link)
            case AgentStage.REVIEW:
                await self._review.run(link)
            case AgentStage.DRAFT:
                await self._draft.run(link)

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
