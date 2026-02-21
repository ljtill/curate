"""Tests for EditionRepository custom query methods."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.database.repositories.editions import EditionRepository
from agent_stack.models.edition import Edition, EditionStatus


@pytest.mark.unit
class TestEditionRepository:
    @pytest.fixture
    def repo(self):
        mock_db = MagicMock()
        mock_container = AsyncMock()
        mock_db.get_container_client.return_value = mock_container
        return EditionRepository(mock_db)

    async def test_get_active_returns_first_result(self, repo):
        edition = Edition(id="ed-1", content={}, status=EditionStatus.CREATED)
        repo.query = AsyncMock(return_value=[edition])

        result = await repo.get_active()

        assert result == edition
        repo.query.assert_called_once()

    async def test_get_active_returns_none_when_empty(self, repo):
        repo.query = AsyncMock(return_value=[])

        result = await repo.get_active()

        assert result is None

    async def test_list_all(self, repo):
        editions = [Edition(id="ed-1", content={}), Edition(id="ed-2", content={})]
        repo.query = AsyncMock(return_value=editions)

        result = await repo.list_all()

        assert len(result) == 2
        repo.query.assert_called_once()

    async def test_list_unpublished(self, repo):
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_unpublished()

        assert result == []
        call_args = repo.query.call_args
        assert "@published" in call_args[0][0]

    async def test_list_published(self, repo):
        repo.query = AsyncMock(return_value=[])

        result = await repo.list_published()

        assert result == []
        call_args = repo.query.call_args
        assert "@status" in call_args[0][0]
