"""Tests for ChangeFeedProcessor."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.pipeline.change_feed import ChangeFeedProcessor

_EXPECTED_HANDLER_CALL_COUNT = 2
_TEST_TOKEN = "new-token"  # noqa: S105


class _FakePageIterator:
    """Simulates AsyncPageIterator returned by AsyncItemPaged.by_page()."""

    def __init__(self, pages: list[list[dict]], token: str | None = None) -> None:
        self._pages = pages
        self.continuation_token = token

    def __aiter__(self) -> None:
        return self._aiter()

    async def _aiter(self) -> None:
        for page in self._pages:

            async def _items(items: list[dict[str, str]] = page) -> None:
                for item in items:
                    yield item

            yield _items()


def _mock_change_feed(pages: list[list[dict]], token: str | None = None) -> None:
    """Create a mock query_items_change_feed that returns an object with by_page()."""

    def factory(**kwargs: Any) -> None:
        factory.last_kwargs = kwargs
        result = MagicMock()
        result.by_page.return_value = _FakePageIterator(pages, token)
        return result

    factory.last_kwargs = {}
    return factory


@pytest.fixture
def mock_orchestrator() -> None:
    """Create a mock orchestrator for testing."""
    orch = AsyncMock()
    orch.handle_link_change = AsyncMock()
    orch.handle_feedback_change = AsyncMock()
    return orch


@pytest.fixture
def processor(mock_orchestrator: AsyncMock) -> tuple[ChangeFeedProcessor, object]:
    """Create a processor for testing."""
    db = MagicMock()
    db.get_container_client = MagicMock(return_value=MagicMock())
    return ChangeFeedProcessor(db, mock_orchestrator)


@pytest.mark.asyncio
async def test_process_feed_delegates_to_handler(processor: ChangeFeedProcessor) -> None:
    """Test that _process_feed calls the handler for each change item."""
    items = [{"id": "link-1"}, {"id": "link-2"}]

    container = MagicMock()
    container.query_items_change_feed = _mock_change_feed([items])
    handler = AsyncMock()

    await processor.process_feed(container, None, handler)

    assert handler.call_count == _EXPECTED_HANDLER_CALL_COUNT
    handler.assert_any_call({"id": "link-1"})
    handler.assert_any_call({"id": "link-2"})


@pytest.mark.asyncio
async def test_process_feed_passes_continuation_token(processor: ChangeFeedProcessor) -> None:
    """Test that continuation token is passed to change feed query."""
    factory = _mock_change_feed([])
    container = MagicMock()
    container.query_items_change_feed = factory

    await processor.process_feed(container, "token-123", AsyncMock())

    assert factory.last_kwargs["continuation"] == "token-123"


@pytest.mark.asyncio
async def test_process_feed_no_token_on_first_call(processor: ChangeFeedProcessor) -> None:
    """Test that no continuation key is passed on the first call."""
    factory = _mock_change_feed([])
    container = MagicMock()
    container.query_items_change_feed = factory

    await processor.process_feed(container, None, AsyncMock())

    assert "continuation" not in factory.last_kwargs


@pytest.mark.asyncio
async def test_process_feed_returns_continuation_token(processor: ChangeFeedProcessor) -> None:
    """Test that the continuation token from the page iterator is returned."""
    container = MagicMock()
    container.query_items_change_feed = _mock_change_feed([], token=_TEST_TOKEN)

    result = await processor.process_feed(container, None, AsyncMock())

    assert result == _TEST_TOKEN


@pytest.mark.asyncio
async def test_process_feed_handles_handler_error(processor: ChangeFeedProcessor) -> None:
    """Test that errors in handler don't stop processing remaining items."""
    items = [{"id": "link-1"}, {"id": "link-2"}]

    container = MagicMock()
    container.query_items_change_feed = _mock_change_feed([items])
    handler = AsyncMock(side_effect=[RuntimeError("fail"), None])

    # Should not raise — errors are caught per item
    await processor.process_feed(container, None, handler)
    assert handler.call_count == _EXPECTED_HANDLER_CALL_COUNT

@pytest.mark.asyncio
async def test_start_creates_background_task(processor: ChangeFeedProcessor) -> None:
    """Verify start creates background task."""
    await processor.start()
    assert processor.running is True
    assert processor.task is not None
    await processor.stop()


@pytest.mark.asyncio
async def test_stop_cancels_task(processor: ChangeFeedProcessor) -> None:
    """Verify stop cancels task."""
    await processor.start()
    await processor.stop()
    assert processor.running is False
