"""Tests for FeedbackRepository custom query methods."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from curate_common.database.repositories.feedback import FeedbackRepository
from curate_common.models.feedback import Feedback


class TestFeedbackRepository:
    """Test the Feedback Repository."""

    @pytest.fixture
    def repo(self) -> FeedbackRepository:
        """Create a repo for testing."""
        mock_db = MagicMock()
        mock_container = AsyncMock()
        mock_db.get_container_client.return_value = mock_container
        return FeedbackRepository(mock_db)

    async def test_get_by_edition(self, repo: FeedbackRepository) -> None:
        """Verify get_by_edition returns feedback for a given edition."""
        fb = Feedback(id="fb-1", edition_id="ed-1", section="intro", comment="Good")
        repo.query = AsyncMock(return_value=[fb])

        result = await repo.get_by_edition("ed-1")

        assert len(result) == 1
        assert result[0].id == "fb-1"
        call_args = repo.query.call_args
        assert "@edition_id" in call_args[0][0]

    async def test_get_by_edition_empty(self, repo: FeedbackRepository) -> None:
        """Verify get_by_edition returns empty list when no feedback found."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_by_edition("ed-missing")

        assert result == []

    async def test_get_unresolved(self, repo: FeedbackRepository) -> None:
        """Verify get_unresolved returns only unresolved feedback."""
        fb = Feedback(
            id="fb-1",
            edition_id="ed-1",
            section="intro",
            comment="Needs work",
        )
        repo.query = AsyncMock(return_value=[fb])

        result = await repo.get_unresolved("ed-1")

        assert len(result) == 1
        call_args = repo.query.call_args
        assert "resolved = false" in call_args[0][0]

    async def test_get_unresolved_empty(self, repo: FeedbackRepository) -> None:
        """Verify get_unresolved returns empty list when all resolved."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_unresolved("ed-1")

        assert result == []
