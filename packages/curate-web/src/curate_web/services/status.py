"""Collect operational statistics for the status page."""

from __future__ import annotations

import asyncio
import platform
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from curate_common import __version__
from curate_common.database.repositories.agent_runs import AgentRunRepository
from curate_common.database.repositories.editions import EditionRepository
from curate_common.database.repositories.feedback import FeedbackRepository
from curate_common.database.repositories.links import LinkRepository

if TYPE_CHECKING:
    from azure.cosmos.aio import DatabaseProxy

    from curate_common.models.agent_run import AgentRun


@dataclass
class AppInfo:
    """Application metadata."""

    version: str
    environment: str
    python_version: str
    platform: str
    uptime: str


@dataclass
class PipelineStats:
    """Aggregate pipeline counts."""

    editions_by_status: dict[str, int] = field(default_factory=dict)
    total_editions: int = 0
    total_links: int = 0
    unresolved_feedback: int = 0


@dataclass
class TokenUsage:
    """Aggregate token consumption."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class StatusInfo:
    """All status information collected for the page."""

    app: AppInfo
    pipeline: PipelineStats
    tokens: TokenUsage
    failures: list[AgentRun]


def _format_uptime(start_time: datetime) -> str:
    """Format a duration as a human-readable string."""
    delta = datetime.now(UTC) - start_time
    total_seconds = int(delta.total_seconds())
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


async def collect_stats(
    database: DatabaseProxy,
    environment: str,
    start_time: datetime,
) -> StatusInfo:
    """Query repositories and assemble operational statistics."""
    editions_repo = EditionRepository(database)
    runs_repo = AgentRunRepository(database)
    links_repo = LinkRepository(database)
    feedback_repo = FeedbackRepository(database)

    (
        edition_counts,
        _run_counts,
        token_totals,
        failures,
        link_count,
        feedback_count,
    ) = await asyncio.gather(
        editions_repo.count_by_status(),
        runs_repo.count_by_status(),
        runs_repo.aggregate_token_usage(),
        runs_repo.list_recent_failures(limit=5),
        links_repo.count_all(),
        feedback_repo.count_all_unresolved(),
    )

    app_info = AppInfo(
        version=__version__,
        environment=environment,
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=platform.machine(),
        uptime=_format_uptime(start_time),
    )

    pipeline = PipelineStats(
        editions_by_status=edition_counts,
        total_editions=sum(edition_counts.values()),
        total_links=link_count,
        unresolved_feedback=feedback_count,
    )

    tokens = TokenUsage(
        input_tokens=token_totals["input_tokens"],
        output_tokens=token_totals["output_tokens"],
        total_tokens=token_totals["total_tokens"],
    )

    return StatusInfo(
        app=app_info,
        pipeline=pipeline,
        tokens=tokens,
        failures=failures,
    )
