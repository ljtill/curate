"""Tests for link route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from curate_common.models.edition import Edition
from curate_common.models.link import Link
from curate_web.routes.links import (
    delete_link,
    list_links,
    retry_link,
    submit_link,
)

_EXPECTED_REDIRECT_STATUS = 303


def _make_request() -> None:
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    return request


async def test_list_links_with_editions() -> None:
    """Verify list links with editions."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})
    links = [Link(id="link-1", url="https://example.com", edition_id="ed-1")]

    with (
        patch("curate_web.routes.links._get_editions_repo") as mock_get_repo,
        patch("curate_web.routes.links.LinkRepository") as mock_links_repo_cls,
        patch("curate_web.routes.links.AgentRunRepository") as mock_runs_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.list_unpublished.return_value = [edition]
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get_by_edition.return_value = links
        mock_links_repo_cls.return_value = links_repo
        runs_repo = AsyncMock()
        runs_repo.get_by_triggers.return_value = []
        mock_runs_repo_cls.return_value = runs_repo

        await list_links(request)

        runs_repo.get_by_triggers.assert_called_once_with(["link-1"])
        request.app.state.templates.TemplateResponse.assert_called_once()
        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == links
        assert ctx["edition"] == edition
        assert ctx["editions"] == [edition]


async def test_list_links_selects_edition_by_query_param() -> None:
    """Verify list links selects edition by query param."""
    request = _make_request()
    ed1 = Edition(id="ed-1", content={})
    ed2 = Edition(id="ed-2", content={})

    with (
        patch("curate_web.routes.links._get_editions_repo") as mock_get_repo,
        patch("curate_web.routes.links.LinkRepository") as mock_links_repo_cls,
        patch("curate_web.routes.links.AgentRunRepository") as mock_runs_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.list_unpublished.return_value = [ed1, ed2]
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get_by_edition.return_value = []
        mock_links_repo_cls.return_value = links_repo
        runs_repo = AsyncMock()
        runs_repo.get_by_triggers.return_value = []
        mock_runs_repo_cls.return_value = runs_repo

        await list_links(request, edition_id="ed-2")

        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["edition"] == ed2


async def test_list_links_without_editions() -> None:
    """Verify list links without editions."""
    request = _make_request()

    with (
        patch("curate_web.routes.links._get_editions_repo") as mock_get_repo,
        patch("curate_web.routes.links.LinkRepository") as mock_links_repo_cls,
        patch("curate_web.routes.links.AgentRunRepository") as mock_runs_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.list_unpublished.return_value = []
        mock_get_repo.return_value = editions_repo
        mock_links_repo_cls.return_value = AsyncMock()
        runs_repo = AsyncMock()
        runs_repo.get_by_triggers.return_value = []
        mock_runs_repo_cls.return_value = runs_repo

        await list_links(request)

        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == []
        assert ctx["edition"] is None
        assert ctx["editions"] == []


async def test_submit_link_creates_link() -> None:
    """Verify submit link creates link."""
    request = _make_request()
    link = Link(id="link-new", url="https://example.com", edition_id="ed-1")

    with patch(
        "curate_web.routes.links.link_svc.submit_link", new_callable=AsyncMock
    ) as mock_submit:
        mock_submit.return_value = link

        response = await submit_link(
            request, url="https://example.com", edition_id="ed-1"
        )

        mock_submit.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_submit_link_redirects_when_no_edition() -> None:
    """Verify submit link redirects when no edition."""
    request = _make_request()

    with patch(
        "curate_web.routes.links.link_svc.submit_link", new_callable=AsyncMock
    ) as mock_submit:
        mock_submit.return_value = None

        response = await submit_link(
            request, url="https://example.com", edition_id="nonexistent"
        )

        mock_submit.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_retry_link_resets_to_submitted() -> None:
    """Verify retry link resets to submitted."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})

    with (
        patch("curate_web.routes.links._get_editions_repo") as mock_get_repo,
        patch(
            "curate_web.routes.links.link_svc.retry_link", new_callable=AsyncMock
        ) as mock_retry,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        mock_retry.return_value = True

        response = await retry_link(request, link_id="link-1")

        mock_retry.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_retry_link_ignores_non_failed() -> None:
    """Verify retry link ignores non failed."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})

    with (
        patch("curate_web.routes.links._get_editions_repo") as mock_get_repo,
        patch(
            "curate_web.routes.links.link_svc.retry_link", new_callable=AsyncMock
        ) as mock_retry,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        mock_retry.return_value = False

        response = await retry_link(request, link_id="link-1")

        mock_retry.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_soft_deletes() -> None:
    """Verify delete link soft-deletes and removes from edition link_ids."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Test"}, link_ids=["link-1"])

    with patch(
        "curate_web.routes.links.link_svc.delete_link", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = edition

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_triggers_regeneration() -> None:
    """Verify deleting a drafted link clears edition content and resets remaining."""
    request = _make_request()
    edition = Edition(
        id="ed-1",
        content={},
        link_ids=["link-2"],
    )

    with patch(
        "curate_web.routes.links.link_svc.delete_link", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = edition

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_no_regeneration_when_not_drafted() -> None:
    """Verify no edition changes when deleted link was never drafted."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Test"}, link_ids=[])

    with patch(
        "curate_web.routes.links.link_svc.delete_link", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = edition

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_redirects_when_not_found() -> None:
    """Verify delete redirects when link not found."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})

    with patch(
        "curate_web.routes.links.link_svc.delete_link", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = edition

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_redirects_for_published_edition() -> None:
    """Verify delete redirects without action for published editions."""
    request = _make_request()

    with patch(
        "curate_web.routes.links.link_svc.delete_link", new_callable=AsyncMock
    ) as mock_delete:
        mock_delete.return_value = None

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        mock_delete.assert_called_once()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS
