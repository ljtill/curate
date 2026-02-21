"""Tests for StaticSiteRenderer — publish_edition workflow."""

from unittest.mock import AsyncMock

import pytest

from agent_stack.models.edition import Edition, EditionStatus
from agent_stack.storage.renderer import StaticSiteRenderer

_EXPECTED_UPLOAD_COUNT = 2


@pytest.mark.unit
class TestStaticSiteRendererPublish:
    """Test the Static Site Renderer Publish."""

    @pytest.fixture
    def renderer(self) -> None:
        """Create a renderer for testing."""
        editions_repo = AsyncMock()
        storage = AsyncMock()
        return StaticSiteRenderer(editions_repo, storage)

    async def test_publish_edition_renders_and_uploads(self, renderer: StaticSiteRenderer) -> None:
        """Verify publish edition renders and uploads."""
        edition = Edition(id="ed-1", content={"title": "Test"}, status=EditionStatus.PUBLISHED)
        renderer.editions_repo.get.return_value = edition
        renderer.editions_repo.list_published.return_value = [edition]

        await renderer.publish_edition("ed-1")

        renderer.editions_repo.get.assert_called_once_with("ed-1", "ed-1")
        assert renderer.storage.upload_html.call_count == _EXPECTED_UPLOAD_COUNT
        # First call: edition page, second call: index page
        calls = renderer.storage.upload_html.call_args_list
        assert calls[0][0][0] == "editions/ed-1.html"
        assert calls[1][0][0] == "index.html"

    async def test_publish_edition_not_found_does_nothing(self, renderer: StaticSiteRenderer) -> None:
        """Verify publish edition not found does nothing."""
        renderer.editions_repo.get.return_value = None

        await renderer.publish_edition("missing")

        renderer.storage.upload_html.assert_not_called()
