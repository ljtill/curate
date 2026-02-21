"""Tests for EditionRepository custom query methods."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.models.edition import Edition, EditionStatus

_EXPECTED_EDITION_COUNT = 2


@pytest.mark.unit
class TestEditionRepository:
    """Test the Edition Repository."""

    @pytest.fixture
    def repo(self) -> EditionRepository:
        """Create a repo for testing."""
        mock_db = MagicMock()
        mock_container = AsyncMock()
        mock_db.get_container_client.return_value = mock_container
        return EditionRepository(mock_db)

    async def test_get_active_returns_first_result(self, repo: EditionRepository) -> None:
        """Verify get active returns first result."""
        edition = Edition(id="ed-1", content={}, status=EditionStatus.CREATED)
        repo.query = AsyncMock(return_value=[edition])

        result = await repo.get_active()

        assert result == edition
        repo.query.assert_called_once()

    async def test_get_active_returns_none_when_empty(self, repo: EditionRepository) -> None:
        """Verify get active returns none when empty."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_active()

        assert result is None

    async def test_list_all(self, repo: EditionRepository) -> None:
        """Verify list all."""
        editions = [Edition(id="ed-1", content={}), Edition(id="ed-2", content={})]
        repo.query = AsyncMock(return_value=editions)

        result = await repo.list_all()

        assert len(result) == _EXPECTED_EDITION_COUNT
        repo.query.assert_called_once()

    async def test_list_unpublished(self, repo: EditionRepository) -> None:
        """Verify list unpublished."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_unpublished()

        assert result == []
        call_args = repo.query.call_args
        assert "@published" in call_args[0][0]

    async def test_list_published(self, repo: EditionRepository) -> None:
        """Verify list published."""
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_published()

        assert result == []
        call_args = repo.query.call_args
        assert "@status" in call_args[0][0]
