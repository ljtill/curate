"""Tests for StaticSiteRenderer — publish_edition workflow."""

from unittest.mock import AsyncMock

import pytest

from curate_common.models.edition import Edition, EditionStatus
from curate_common.storage.renderer import StaticSiteRenderer

_EXPECTED_ADJACENT_UPLOAD_COUNT = 4
_EXPECTED_SINGLE_UPLOAD_COUNT = 2


class TestStaticSiteRendererPublish:
    """Test the Static Site Renderer Publish."""

    @pytest.fixture
    def renderer(self) -> None:
        """Create a renderer for testing."""
        editions_repo = AsyncMock()
        storage = AsyncMock()
        return StaticSiteRenderer(editions_repo, storage)

    async def test_publish_edition_renders_and_uploads(
        self, renderer: StaticSiteRenderer
    ) -> None:
        """Verify publish edition renders and uploads."""
        edition = Edition(
            id="ed-1", content={"title": "Test"}, status=EditionStatus.PUBLISHED
        )
        renderer.editions_repo.get.return_value = edition
        renderer.editions_repo.list_published.return_value = [edition]

        await renderer.publish_edition("ed-1")

        renderer.editions_repo.get.assert_called_once_with("ed-1", "ed-1")
        assert renderer.storage.upload_html.call_count == _EXPECTED_SINGLE_UPLOAD_COUNT
        calls = renderer.storage.upload_html.call_args_list
        assert calls[0][0][0] == "editions/ed-1.html"
        assert calls[1][0][0] == "index.html"

    async def test_publish_edition_rerenders_adjacent(
        self, renderer: StaticSiteRenderer
    ) -> None:
        """Verify publish re-renders adjacent editions for prev/next nav."""
        editions = [
            Edition(
                id="ed-3",
                content={"title": "Newest"},
                status=EditionStatus.PUBLISHED,
            ),
            Edition(
                id="ed-2",
                content={"title": "Middle"},
                status=EditionStatus.PUBLISHED,
            ),
            Edition(
                id="ed-1",
                content={"title": "Oldest"},
                status=EditionStatus.PUBLISHED,
            ),
        ]
        renderer.editions_repo.get.return_value = editions[1]
        renderer.editions_repo.list_published.return_value = editions

        await renderer.publish_edition("ed-2")

        upload_count = renderer.storage.upload_html.call_count
        assert upload_count == _EXPECTED_ADJACENT_UPLOAD_COUNT
        blob_names = [c[0][0] for c in renderer.storage.upload_html.call_args_list]
        assert "editions/ed-2.html" in blob_names
        assert "editions/ed-3.html" in blob_names
        assert "editions/ed-1.html" in blob_names
        assert "index.html" in blob_names

    async def test_publish_edition_not_found_does_nothing(
        self, renderer: StaticSiteRenderer
    ) -> None:
        """Verify publish edition not found does nothing."""
        renderer.editions_repo.get.return_value = None

        await renderer.publish_edition("missing")

        renderer.storage.upload_html.assert_not_called()
