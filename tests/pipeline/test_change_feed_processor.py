"""Tests for the ChangeFeedProcessor — poll loop and feed processing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from azure.core.exceptions import ServiceResponseError

from agent_stack.pipeline.change_feed import ChangeFeedProcessor

_TEST_CONTINUATION_TOKEN = "token-abc"  # noqa: S105
_TEST_CONTINUATION_TOKEN_SHORT = "token"  # noqa: S105


class _SingleItemPage:
    """Async iterable page that yields items one at a time."""

    def __init__(self, items: list[dict[str, str]]) -> None:
        self._items = iter(items)

    def __aiter__(self) -> "_SingleItemPage":
        return self

    async def __anext__(self) -> dict[str, str]:
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration from None


class _MockPageIterator:
    """Async iterable over pages with a continuation token."""

    def __init__(self, pages: list[object], continuation_token: str = "") -> None:
        self._pages = iter(pages)
        self.continuation_token = continuation_token

    def __aiter__(self) -> "_MockPageIterator":
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._pages)
        except StopIteration:
            raise StopAsyncIteration from None


@pytest.mark.unit
class TestChangeFeedProcessor:
    """Test the Change Feed Processor."""

    @pytest.fixture
    def mock_database(self) -> MagicMock:
        """Create a mock database for testing."""
        return MagicMock()

    @pytest.fixture
    def mock_orchestrator(self) -> None:
        """Create a mock orchestrator for testing."""
        orch = MagicMock()
        orch.handle_link_change = AsyncMock()
        orch.handle_feedback_change = AsyncMock()
        return orch

    @pytest.fixture
    def processor(self, mock_database: MagicMock, mock_orchestrator: MagicMock) -> tuple[ChangeFeedProcessor, object]:
        """Create a processor for testing."""
        return ChangeFeedProcessor(mock_database, mock_orchestrator)

    async def test_start_creates_background_task(self, processor: ChangeFeedProcessor) -> None:
        """Verify start creates background task."""
        # Prevent the actual poll loop from running
        with patch.object(processor, "_poll_loop", new_callable=AsyncMock):
            await processor.start()

            assert processor.running is True
            assert processor.task is not None

            await processor.stop()

    async def test_stop_cancels_task(self, processor: ChangeFeedProcessor) -> None:
        """Verify stop cancels task."""
        with patch.object(processor, "_poll_loop", new_callable=AsyncMock):
            await processor.start()
            await processor.stop()

            assert processor.running is False

    async def test_process_feed_calls_handler(self, processor: ChangeFeedProcessor) -> None:
        """Verify process feed calls handler."""
        mock_container = MagicMock()

        item = {"id": "link-1", "status": "submitted"}

        page_iter = _MockPageIterator(
            [_SingleItemPage([item])], continuation_token=_TEST_CONTINUATION_TOKEN
        )

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        handler = AsyncMock()
        result = await processor.process_feed(mock_container, None, handler)

        handler.assert_awaited_once_with(item)
        assert result == _TEST_CONTINUATION_TOKEN

    async def test_process_feed_with_continuation_token(self, processor: ChangeFeedProcessor) -> None:
        """Verify process feed with continuation token."""
        mock_container = MagicMock()

        class EmptyPageIterator:
            continuation_token = None

            def __aiter__(self) -> None:
                return self

            async def __anext__(self) -> None:
                raise StopAsyncIteration from None

        page_iter = EmptyPageIterator()

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        result = await processor.process_feed(mock_container, "prev-token", AsyncMock())

        call_kwargs = mock_container.query_items_change_feed.call_args[1]
        assert call_kwargs["continuation"] == "prev-token"
        assert result == "prev-token"

    async def test_process_feed_handles_item_error(self, processor: ChangeFeedProcessor) -> None:
        """Verify process feed handles item error."""
        mock_container = MagicMock()

        item = {"id": "link-1"}

        page_iter = _MockPageIterator(
            [_SingleItemPage([item])], continuation_token=_TEST_CONTINUATION_TOKEN_SHORT
        )

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        handler = AsyncMock(side_effect=Exception("handler error"))
        result = await processor.process_feed(mock_container, None, handler)

        assert result == _TEST_CONTINUATION_TOKEN_SHORT

    async def test_process_feed_handles_emulator_http_error(self, processor: ChangeFeedProcessor) -> None:
        """Verify process feed handles emulator http error."""
        mock_container = MagicMock()

        class ErrorPageIterator:
            continuation_token = None

            def __aiter__(self) -> None:
                return self

            async def __anext__(self) -> None:
                raise ServiceResponseError("Expected HTTP/ blah")

        page_iter = ErrorPageIterator()

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        result = await processor.process_feed(mock_container, "old-token", AsyncMock())

        assert result == "old-token"
