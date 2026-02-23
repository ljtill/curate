"""Tests for dashboard service functions."""

from unittest.mock import AsyncMock, MagicMock

from curate_web.services.dashboard import get_dashboard_data


async def test_get_dashboard_data_returns_editions_and_runs() -> None:
    """Verify get_dashboard_data returns editions, active_edition, and recent_runs."""
    editions_repo = MagicMock()
    runs_repo = MagicMock()
    fake_editions = [MagicMock(), MagicMock()]
    fake_active = MagicMock()
    fake_runs = [MagicMock()]
    editions_repo.list_all = AsyncMock(return_value=fake_editions)
    editions_repo.get_active = AsyncMock(return_value=fake_active)
    runs_repo.list_recent = AsyncMock(return_value=fake_runs)

    result = await get_dashboard_data(editions_repo, runs_repo)

    assert result["editions"] == fake_editions
    assert result["active_edition"] == fake_active
    assert result["recent_runs"] == fake_runs
    editions_repo.list_all.assert_awaited_once()
    editions_repo.get_active.assert_awaited_once()
    runs_repo.list_recent.assert_awaited_once_with(5)
