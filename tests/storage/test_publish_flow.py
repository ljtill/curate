"""Tests for StaticSiteRenderer — publish_edition workflow."""

from unittest.mock import AsyncMock

import pytest

from agent_stack.models.edition import Edition, EditionStatus
from agent_stack.storage.renderer import StaticSiteRenderer


@pytest.mark.unit
class TestStaticSiteRendererPublish:
    @pytest.fixture
    def renderer(self):
        editions_repo = AsyncMock()
        storage = AsyncMock()
        r = StaticSiteRenderer(editions_repo, storage)
        return r

    async def test_publish_edition_renders_and_uploads(self, renderer):
        edition = Edition(id="ed-1", content={"title": "Test"}, status=EditionStatus.PUBLISHED)
        renderer._editions_repo.get.return_value = edition
        renderer._editions_repo.list_published.return_value = [edition]

        await renderer.publish_edition("ed-1")

        renderer._editions_repo.get.assert_called_once_with("ed-1", "ed-1")
        assert renderer._storage.upload_html.call_count == 2
        # First call: edition page, second call: index page
        calls = renderer._storage.upload_html.call_args_list
        assert calls[0][0][0] == "editions/ed-1.html"
        assert calls[1][0][0] == "index.html"

    async def test_publish_edition_not_found_does_nothing(self, renderer):
        renderer._editions_repo.get.return_value = None

        await renderer.publish_edition("missing")

        renderer._storage.upload_html.assert_not_called()
