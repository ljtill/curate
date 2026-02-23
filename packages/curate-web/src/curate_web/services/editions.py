"""Edition business logic — create, detail assembly, publish, delete."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from curate_common.models.edition import Edition

if TYPE_CHECKING:
    from curate_common.database.repositories.agent_runs import AgentRunRepository
    from curate_common.database.repositories.editions import EditionRepository
    from curate_common.database.repositories.feedback import FeedbackRepository
    from curate_common.database.repositories.links import LinkRepository
    from curate_common.events import EventPublisher
    from curate_common.models.link import Link

logger = logging.getLogger(__name__)


async def list_editions(editions_repo: EditionRepository) -> list[Edition]:
    """Return all editions."""
    return await editions_repo.list_all()


async def get_edition(
    edition_id: str, editions_repo: EditionRepository
) -> Edition | None:
    """Return a single edition by ID, or None if not found."""
    return await editions_repo.get(edition_id, edition_id)


async def create_edition(editions_repo: EditionRepository) -> Edition:
    """Auto-generate an issue number and create a new edition."""
    issue_number = await editions_repo.next_issue_number()
    edition = Edition(
        content={
            "title": f"Issue #{issue_number}",
            "issue_number": issue_number,
            "sections": [],
        }
    )
    await editions_repo.create(edition)
    return edition


async def get_edition_detail(
    edition_id: str,
    editions_repo: EditionRepository,
    links_repo: LinkRepository,
    agent_runs_repo: AgentRunRepository,
) -> dict[str, Any]:
    """Fetch edition, links, and agent runs and assemble a detail dict."""
    started_at = time.monotonic()
    edition = await editions_repo.get(edition_id, edition_id)
    links: list[Link] = await links_repo.get_by_edition(edition_id) if edition else []

    trigger_ids = [link.id for link in links]
    agent_runs = (
        await agent_runs_repo.get_by_triggers(trigger_ids) if trigger_ids else []
    )
    links_by_id = {link.id: link for link in links}

    logger.info(
        "Edition detail assembled — edition=%s exists=%s links=%d "
        "triggers=%d runs=%d duration_ms=%.0f",
        edition_id,
        edition is not None,
        len(links),
        len(trigger_ids),
        len(agent_runs),
        (time.monotonic() - started_at) * 1000,
    )

    return {
        "edition": edition,
        "links": links,
        "agent_runs": agent_runs,
        "links_by_id": links_by_id,
    }


async def get_workspace_data(
    edition_id: str,
    editions_repo: EditionRepository,
    links_repo: LinkRepository,
    agent_runs_repo: AgentRunRepository,
    feedback_repo: FeedbackRepository,
) -> dict[str, Any]:
    """Fetch all data needed for the edition workspace view."""
    started_at = time.monotonic()
    edition = await editions_repo.get(edition_id, edition_id)
    links: list[Link] = await links_repo.get_by_edition(edition_id) if edition else []
    unattached_links = await links_repo.list_unattached()
    agent_runs = await agent_runs_repo.list_by_edition(edition_id)
    feedback = await feedback_repo.get_by_edition(edition_id)
    links_by_id = {link.id: link for link in links}

    logger.info(
        "Workspace data assembled — edition=%s exists=%s links=%d "
        "unattached=%d runs=%d feedback=%d duration_ms=%.0f",
        edition_id,
        edition is not None,
        len(links),
        len(unattached_links),
        len(agent_runs),
        len(feedback),
        (time.monotonic() - started_at) * 1000,
    )

    return {
        "edition": edition,
        "links": links,
        "unattached_links": unattached_links,
        "agent_runs": agent_runs,
        "feedback": feedback,
        "links_by_id": links_by_id,
    }


async def publish_edition(
    edition_id: str,
    event_publisher: EventPublisher,
) -> None:
    """Request edition publish via Service Bus command."""
    await event_publisher.publish("publish-request", {"edition_id": edition_id})


async def delete_edition(edition_id: str, editions_repo: EditionRepository) -> None:
    """Soft-delete an edition if it exists."""
    edition = await editions_repo.get(edition_id, edition_id)
    if edition:
        await editions_repo.soft_delete(edition, edition_id)
