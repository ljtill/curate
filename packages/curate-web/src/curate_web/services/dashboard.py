"""Dashboard service — data assembly for the dashboard overview page."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from curate_common.database.repositories.agent_runs import AgentRunRepository
    from curate_common.database.repositories.editions import EditionRepository


async def get_dashboard_data(
    editions_repo: EditionRepository,
    runs_repo: AgentRunRepository,
) -> dict[str, Any]:
    """Fetch editions and recent agent runs for the dashboard overview."""
    editions = await editions_repo.list_all()
    active_edition = await editions_repo.get_active()
    recent_runs = await runs_repo.list_recent(5)
    return {
        "editions": editions,
        "active_edition": active_edition,
        "recent_runs": recent_runs,
    }
