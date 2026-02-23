"""Tests for LinkRepository custom query methods."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from curate_common.database.repositories.links import LinkRepository
from curate_common.models.link import Link, LinkStatus


class TestLinkRepository:
    """Test the Link Repository."""

    @pytest.fixture
    def repo(self) -> LinkRepository:
        """Create a repo for testing."""
        mock_db = MagicMock()
        mock_container = AsyncMock()
        mock_db.get_container_client.return_value = mock_container
        return LinkRepository(mock_db)

    async def test_get_by_edition(self, repo: LinkRepository) -> None:
        """Verify get_by_edition returns links for a given edition."""
        link = Link(id="link-1", url="https://example.com", edition_id="ed-1")
        repo.query = AsyncMock(return_value=[link])

        result = await repo.get_by_edition("ed-1")

        assert len(result) == 1
        assert result[0].id == "link-1"
        call_args = repo.query.call_args
        assert "@edition_id" in call_args[0][0]

    async def test_get_by_edition_empty(self, repo: LinkRepository) -> None:
        """Verify get_by_edition returns empty list when no links found."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_by_edition("ed-missing")

        assert result == []

    async def test_get_by_status(self, repo: LinkRepository) -> None:
        """Verify get_by_status filters by edition and status."""
        link = Link(
            id="link-1",
            url="https://example.com",
            edition_id="ed-1",
            status=LinkStatus.REVIEWED,
        )
        repo.query = AsyncMock(return_value=[link])

        result = await repo.get_by_status("ed-1", LinkStatus.REVIEWED)

        assert len(result) == 1
        call_args = repo.query.call_args
        assert "@edition_id" in call_args[0][0]
        assert "@status" in call_args[0][0]
        params = call_args[0][1]
        status_param = next(p for p in params if p["name"] == "@status")
        assert status_param["value"] == LinkStatus.REVIEWED.value

    async def test_get_by_status_empty(self, repo: LinkRepository) -> None:
        """Verify get_by_status returns empty list when no matching links."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_by_status("ed-1", LinkStatus.SUBMITTED)

        assert result == []
