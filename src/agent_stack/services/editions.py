"""Edition business logic — create, detail assembly, publish, delete, title update."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_stack.models.edition import Edition

if TYPE_CHECKING:
    from agent_stack.database.repositories.agent_runs import AgentRunRepository
    from agent_stack.database.repositories.editions import EditionRepository
    from agent_stack.database.repositories.links import LinkRepository
    from agent_stack.models.link import Link
    from agent_stack.pipeline.orchestrator import PipelineOrchestrator


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
    edition = await editions_repo.get(edition_id, edition_id)
    links: list[Link] = await links_repo.get_by_edition(edition_id) if edition else []

    trigger_ids = [link.id for link in links]
    agent_runs = (
        await agent_runs_repo.get_by_triggers(trigger_ids) if trigger_ids else []
    )
    links_by_id = {link.id: link for link in links}

    return {
        "edition": edition,
        "links": links,
        "agent_runs": agent_runs,
        "links_by_id": links_by_id,
    }


async def publish_edition(edition_id: str, orchestrator: PipelineOrchestrator) -> None:
    """Invoke the orchestrator publish pipeline."""
    await orchestrator.handle_publish(edition_id)


async def delete_edition(edition_id: str, editions_repo: EditionRepository) -> None:
    """Soft-delete an edition if it exists."""
    edition = await editions_repo.get(edition_id, edition_id)
    if edition:
        await editions_repo.soft_delete(edition, edition_id)


async def update_title(
    edition_id: str, title: str, editions_repo: EditionRepository
) -> Edition | None:
    """Update the title in an edition's content dict."""
    edition = await editions_repo.get(edition_id, edition_id)
    if edition:
        edition.content["title"] = title.strip()
        await editions_repo.update(edition, edition_id)
    return edition
