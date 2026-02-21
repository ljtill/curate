"""Tests for the ChangeFeedProcessor — poll loop and feed processing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.pipeline.change_feed import ChangeFeedProcessor


@pytest.mark.unit
class TestChangeFeedProcessor:
    @pytest.fixture
    def mock_database(self):
        return MagicMock()

    @pytest.fixture
    def mock_orchestrator(self):
        orch = MagicMock()
        orch.handle_link_change = AsyncMock()
        orch.handle_feedback_change = AsyncMock()
        return orch

    @pytest.fixture
    def processor(self, mock_database, mock_orchestrator):
        return ChangeFeedProcessor(mock_database, mock_orchestrator)

    async def test_start_creates_background_task(self, processor):
        # Prevent the actual poll loop from running
        with patch.object(processor, "_poll_loop", new_callable=AsyncMock):
            await processor.start()

            assert processor._running is True
            assert processor._task is not None

            await processor.stop()

    async def test_stop_cancels_task(self, processor):
        with patch.object(processor, "_poll_loop", new_callable=AsyncMock):
            await processor.start()
            await processor.stop()

            assert processor._running is False

    async def test_process_feed_calls_handler(self, processor):
        mock_container = MagicMock()

        item = {"id": "link-1", "status": "submitted"}

        class MockPage:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration from None

        class MockPageIterator:
            def __init__(self, pages):
                self._pages = iter(pages)
                self.continuation_token = "token-abc"

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._pages)
                except StopIteration:
                    raise StopAsyncIteration from None

        class SingleItemPage:
            def __init__(self, items):
                self._items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration from None

        page_iter = MockPageIterator([SingleItemPage([item])])

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        handler = AsyncMock()
        result = await processor._process_feed(mock_container, None, handler)

        handler.assert_awaited_once_with(item)
        assert result == "token-abc"

    async def test_process_feed_with_continuation_token(self, processor):
        mock_container = MagicMock()

        class EmptyPageIterator:
            continuation_token = None

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration from None

        page_iter = EmptyPageIterator()

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        result = await processor._process_feed(mock_container, "prev-token", AsyncMock())

        call_kwargs = mock_container.query_items_change_feed.call_args[1]
        assert call_kwargs["continuation"] == "prev-token"
        assert result == "prev-token"

    async def test_process_feed_handles_item_error(self, processor):
        mock_container = MagicMock()

        item = {"id": "link-1"}

        class SingleItemPage:
            def __init__(self, items):
                self._items = iter(items)

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._items)
                except StopIteration:
                    raise StopAsyncIteration from None

        class MockPageIterator:
            def __init__(self, pages):
                self._pages = iter(pages)
                self.continuation_token = "token"

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._pages)
                except StopIteration:
                    raise StopAsyncIteration from None

        page_iter = MockPageIterator([SingleItemPage([item])])

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        handler = AsyncMock(side_effect=Exception("handler error"))
        result = await processor._process_feed(mock_container, None, handler)

        assert result == "token"

    async def test_process_feed_handles_emulator_http_error(self, processor):
        from azure.core.exceptions import ServiceResponseError

        mock_container = MagicMock()

        class ErrorPageIterator:
            continuation_token = None

            def __aiter__(self):
                return self

            async def __anext__(self):
                raise ServiceResponseError("Expected HTTP/ blah")

        page_iter = ErrorPageIterator()

        mock_response = MagicMock()
        mock_response.by_page.return_value = page_iter
        mock_container.query_items_change_feed.return_value = mock_response

        result = await processor._process_feed(mock_container, "old-token", AsyncMock())

        assert result == "old-token"
