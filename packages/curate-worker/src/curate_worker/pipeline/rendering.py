"""SSE / HTML rendering helpers for pipeline status updates."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from curate_common.models.link import Link

_DISPLAY_URL_MAX_LENGTH = 50


def render_link_row(link: Link, runs: list) -> str:
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
