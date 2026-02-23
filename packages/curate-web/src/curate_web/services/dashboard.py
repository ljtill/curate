"""Dashboard service — data assembly for the dashboard overview page."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from curate_common.database.repositories.agent_runs import AgentRunRepository
    from curate_common.models.agent_run import AgentRun


async def get_dashboard_data(
    runs_repo: AgentRunRepository,
) -> dict[str, list[AgentRun]]:
    """Fetch recent agent runs for the dashboard overview."""
    recent_runs = await runs_repo.list_recent(5)
    return {"recent_runs": recent_runs}
