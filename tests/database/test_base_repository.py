"""Tests for BaseRepository with mocked Cosmos DB container."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.database.repositories.base import BaseRepository
from agent_stack.models.link import Link


class ConcreteRepo(BaseRepository[Link]):
    container_name = "links"
    model_class = Link


@pytest.fixture
def mock_container():
    return AsyncMock()


@pytest.fixture
def repo(mock_container):
    db = MagicMock()
    db.get_container_client.return_value = mock_container
    return ConcreteRepo(db)


@pytest.mark.asyncio
async def test_create_calls_create_item(repo, mock_container):
    link = Link(url="https://example.com", edition_id="ed-1")
    result = await repo.create(link)
    assert result is link
    mock_container.create_item.assert_called_once()
    body = mock_container.create_item.call_args[1]["body"]
    assert body["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_get_returns_model_on_success(repo, mock_container):
    mock_container.read_item.return_value = {
        "id": "link-1",
        "url": "https://example.com",
        "edition_id": "ed-1",
        "status": "submitted",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    result = await repo.get("link-1", "ed-1")
    assert result is not None
    assert result.id == "link-1"
    assert result.url == "https://example.com"


@pytest.mark.asyncio
async def test_get_returns_none_on_exception(repo, mock_container):
    mock_container.read_item.side_effect = Exception("Not found")
    result = await repo.get("missing", "ed-1")
    assert result is None


@pytest.mark.asyncio
async def test_get_returns_none_for_soft_deleted(repo, mock_container):
    mock_container.read_item.return_value = {
        "id": "link-1",
        "url": "https://example.com",
        "edition_id": "ed-1",
        "status": "submitted",
        "deleted_at": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    result = await repo.get("link-1", "ed-1")
    assert result is None


@pytest.mark.asyncio
async def test_update_sets_updated_at(repo, mock_container):
    link = Link(url="https://example.com", edition_id="ed-1")
    original_updated = link.updated_at
    result = await repo.update(link, "ed-1")
    assert result.updated_at >= original_updated
    call_kwargs = mock_container.replace_item.call_args[1]
    assert "partition_key" not in call_kwargs


@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at(repo, mock_container):
    link = Link(url="https://example.com", edition_id="ed-1")
    assert link.deleted_at is None
    result = await repo.soft_delete(link, "ed-1")
    assert result.deleted_at is not None
    mock_container.replace_item.assert_called_once()


@pytest.mark.asyncio
async def test_query_filters_soft_deleted(repo, mock_container):
    items = [
        {
            "id": "link-1",
            "url": "https://a.com",
            "edition_id": "ed-1",
            "status": "submitted",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        {
            "id": "link-2",
            "url": "https://b.com",
            "edition_id": "ed-1",
            "status": "submitted",
            "deleted_at": "2026-01-01T00:00:00+00:00",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    ]

    async def mock_query_items(**kwargs):
        for item in items:
            yield item

    mock_container.query_items = mock_query_items
    results = await repo.query("SELECT * FROM c")
    assert len(results) == 1
    assert results[0].id == "link-1"
