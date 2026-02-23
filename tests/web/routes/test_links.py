"""Tests for store route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_common.models.link import Link
from curate_web.routes.links import (
    delete_link,
    list_store,
    retry_link,
    submit_link,
)
from tests.web.routes.runtime_helpers import make_runtime

_EXPECTED_REDIRECT_STATUS = 303


def _make_request() -> None:
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    request.app.state.runtime = make_runtime(
        cosmos=request.app.state.cosmos,
        templates=request.app.state.templates,
    )
    return request


async def test_list_store_renders_all_links() -> None:
    """Verify store page lists all links."""
    request = _make_request()
    links = [Link(id="link-1", url="https://example.com")]

    with patch("curate_web.routes.links.get_link_repository") as mock_links_repo:
        links_repo = AsyncMock()
        links_repo.list_all.return_value = links
        mock_links_repo.return_value = links_repo

        await list_store(request)

        links_repo.list_all.assert_called_once()
        request.app.state.templates.TemplateResponse.assert_called_once()
        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == links


async def test_list_store_empty() -> None:
    """Verify store page handles no links."""
    request = _make_request()

    with patch("curate_web.routes.links.get_link_repository") as mock_links_repo:
        links_repo = AsyncMock()
        links_repo.list_all.return_value = []
        mock_links_repo.return_value = links_repo

        await list_store(request)

        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == []


async def test_submit_link_creates_link() -> None:
    """Verify submit link creates link in the global store."""
    request = _make_request()
    link = Link(id="link-new", url="https://example.com")

    with patch(
        "curate_web.routes.links.link_svc.submit_link", new_callable=AsyncMock
    ) as mock_submit:
        mock_submit.return_value = link

        response = await submit_link(request, url="https://example.com")

        mock_submit.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_retry_link_resets_to_submitted() -> None:
    """Verify retry link resets to submitted."""
    request = _make_request()

    with patch(
        "curate_web.routes.links.link_svc.retry_link", new_callable=AsyncMock
    ) as mock_retry:
        mock_retry.return_value = True

        response = await retry_link(request, link_id="link-1")

        mock_retry.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_retry_link_ignores_non_failed() -> None:
    """Verify retry link ignores non-failed."""
    request = _make_request()

    with patch(
        "curate_web.routes.links.link_svc.retry_link", new_callable=AsyncMock
    ) as mock_retry:
        mock_retry.return_value = False

        response = await retry_link(request, link_id="link-1")

        mock_retry.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_soft_deletes() -> None:
    """Verify delete link soft-deletes."""
    request = _make_request()

    with patch(
        "curate_web.routes.links.link_svc.delete_link", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = None

        response = await delete_link(request, link_id="link-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS
