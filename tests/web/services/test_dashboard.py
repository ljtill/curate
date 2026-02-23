"""Tests for dashboard service functions."""

from unittest.mock import AsyncMock, MagicMock

from curate_web.services.dashboard import get_dashboard_data


async def test_get_dashboard_data_returns_recent_runs() -> None:
    """Verify get_dashboard_data returns recent_runs from repo."""
    runs_repo = MagicMock()
    fake_runs = [MagicMock(), MagicMock()]
    runs_repo.list_recent = AsyncMock(return_value=fake_runs)

    result = await get_dashboard_data(runs_repo)

    assert result["recent_runs"] == fake_runs
    runs_repo.list_recent.assert_awaited_once_with(5)
