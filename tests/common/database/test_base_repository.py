"""Tests for BaseRepository with mocked Cosmos DB container."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.cosmos.exceptions import CosmosHttpResponseError

from curate_common.database.repositories.base import BaseRepository
from curate_common.models.link import Link


class ConcreteRepo(BaseRepository[Link]):
    """Test the Concrete Repo."""

    container_name = "links"
    model_class = Link


@pytest.fixture
def mock_container() -> AsyncMock:
    """Create a mock container."""
    return AsyncMock()


@pytest.fixture
def repo(mock_container: AsyncMock) -> ConcreteRepo:
    """Create a repo for testing."""
    db = MagicMock()
    db.get_container_client.return_value = mock_container
    return ConcreteRepo(db)


async def test_create_calls_create_item(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify create calls create item."""
    link = Link(url="https://example.com", edition_id="ed-1")
    result = await repo.create(link)
    assert result is link
    mock_container.create_item.assert_called_once()
    body = mock_container.create_item.call_args[1]["body"]
    assert body["url"] == "https://example.com"


async def test_get_returns_model_on_success(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify get returns model on success."""
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


async def test_get_returns_none_on_exception(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify get returns none on exception."""
    mock_container.read_item.side_effect = CosmosHttpResponseError(
        status_code=404, message="Not found"
    )
    result = await repo.get("missing", "ed-1")
    assert result is None


async def test_get_returns_none_for_soft_deleted(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify get returns none for soft deleted."""
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


async def test_update_sets_updated_at(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify update sets updated at."""
    link = Link(url="https://example.com", edition_id="ed-1")
    original_updated = link.updated_at
    result = await repo.update(link, "ed-1")
    assert result.updated_at >= original_updated
    call_kwargs = mock_container.replace_item.call_args[1]
    assert "partition_key" not in call_kwargs


async def test_soft_delete_sets_deleted_at(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify soft delete sets deleted at."""
    link = Link(url="https://example.com", edition_id="ed-1")
    assert link.deleted_at is None
    result = await repo.soft_delete(link, "ed-1")
    assert result.deleted_at is not None
    mock_container.replace_item.assert_called_once()


async def test_query_filters_soft_deleted(
    repo: ConcreteRepo, mock_container: AsyncMock
) -> None:
    """Verify query filters soft deleted."""
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

    async def mock_query_items(**_kwargs: Any) -> None:
        for item in items:
            yield item

    mock_container.query_items = mock_query_items
    results = await repo.query("SELECT * FROM c")
    assert len(results) == 1
    assert results[0].id == "link-1"


async def test_query_logs_warning_when_slow(
    mock_container: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify slow query logs warning diagnostics."""
    monkeypatch.setenv("APP_SLOW_REPOSITORY_MS", "0")
    db = MagicMock()
    db.get_container_client.return_value = mock_container
    repo = ConcreteRepo(db)

    async def mock_query_items(**_kwargs: Any) -> None:
        yield {
            "id": "link-1",
            "url": "https://a.com",
            "edition_id": "ed-1",
            "status": "submitted",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }

    mock_container.query_items = mock_query_items

    with patch(
        "curate_common.database.repositories.base.logger.warning"
    ) as mock_warning:
        await repo.query("SELECT * FROM c")

    mock_warning.assert_called_once()
