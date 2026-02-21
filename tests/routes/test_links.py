"""Tests for link route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from agent_stack.models.edition import Edition, EditionStatus
from agent_stack.models.link import Link, LinkStatus
from agent_stack.routes.links import delete_link, list_links, retry_link, submit_link

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
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.list_unpublished.return_value = [edition]
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get_by_edition.return_value = links
        mock_links_repo_cls.return_value = links_repo

        await list_links(request)

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
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.list_unpublished.return_value = [ed1, ed2]
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get_by_edition.return_value = []
        mock_links_repo_cls.return_value = links_repo

        await list_links(request, edition_id="ed-2")

        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["edition"] == ed2


async def test_list_links_without_editions() -> None:
    """Verify list links without editions."""
    request = _make_request()

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.list_unpublished.return_value = []
        mock_get_repo.return_value = editions_repo
        mock_links_repo_cls.return_value = AsyncMock()

        await list_links(request)

        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == []
        assert ctx["edition"] is None
        assert ctx["editions"] == []


async def test_submit_link_creates_link() -> None:
    """Verify submit link creates link."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        mock_links_repo_cls.return_value = links_repo

        response = await submit_link(
            request, url="https://example.com", edition_id="ed-1"
        )

        links_repo.create.assert_called_once()
        created = links_repo.create.call_args[0][0]
        assert created.url == "https://example.com"
        assert created.edition_id == "ed-1"
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_submit_link_redirects_when_no_edition() -> None:
    """Verify submit link redirects when no edition."""
    request = _make_request()

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = None
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        mock_links_repo_cls.return_value = links_repo

        response = await submit_link(
            request, url="https://example.com", edition_id="nonexistent"
        )

        links_repo.create.assert_not_called()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_retry_link_resets_to_submitted() -> None:
    """Verify retry link resets to submitted."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.FAILED,
    )

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        mock_links_repo_cls.return_value = links_repo

        response = await retry_link(request, link_id="link-1")

        assert link.status == LinkStatus.SUBMITTED
        assert link.title is None
        assert link.content is None
        links_repo.update.assert_called_once_with(link, "ed-1")
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_retry_link_ignores_non_failed() -> None:
    """Verify retry link ignores non failed."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.SUBMITTED,
    )

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        mock_links_repo_cls.return_value = links_repo

        response = await retry_link(request, link_id="link-1")

        links_repo.update.assert_not_called()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_soft_deletes() -> None:
    """Verify delete link soft-deletes and removes from edition link_ids."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Test"}, link_ids=["link-1"])
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.DRAFTED,
    )

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        links_repo.get_by_status.return_value = []
        mock_links_repo_cls.return_value = links_repo

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        links_repo.soft_delete.assert_called_once_with(link, "ed-1")
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_triggers_regeneration() -> None:
    """Verify deleting a drafted link clears edition content and resets remaining."""
    request = _make_request()
    edition = Edition(
        id="ed-1",
        content={"title": "Test"},
        link_ids=["link-1", "link-2"],
    )
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.DRAFTED,
    )
    remaining = Link(
        id="link-2",
        url="https://other.com",
        edition_id="ed-1",
        status=LinkStatus.DRAFTED,
    )

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        links_repo.get_by_status.return_value = [remaining]
        mock_links_repo_cls.return_value = links_repo

        await delete_link(request, link_id="link-1", edition_id="ed-1")

        # Edition content cleared, link_id removed
        assert edition.content == {}
        assert "link-1" not in edition.link_ids
        assert "link-2" in edition.link_ids
        editions_repo.update.assert_called_once_with(edition, "ed-1")

        # Remaining drafted link reset to REVIEWED
        assert remaining.status == LinkStatus.REVIEWED
        links_repo.update.assert_called_once_with(remaining, "ed-1")


async def test_delete_link_no_regeneration_when_not_drafted() -> None:
    """Verify no edition changes when deleted link was never drafted."""
    request = _make_request()
    edition = Edition(id="ed-1", content={"title": "Test"}, link_ids=[])
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        status=LinkStatus.SUBMITTED,
    )

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        mock_links_repo_cls.return_value = links_repo

        await delete_link(request, link_id="link-1", edition_id="ed-1")

        links_repo.soft_delete.assert_called_once()
        editions_repo.update.assert_not_called()
        assert edition.content == {"title": "Test"}


async def test_delete_link_redirects_when_not_found() -> None:
    """Verify delete redirects when link not found."""
    request = _make_request()
    edition = Edition(id="ed-1", content={})

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = None
        mock_links_repo_cls.return_value = links_repo

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        links_repo.soft_delete.assert_not_called()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS


async def test_delete_link_redirects_for_published_edition() -> None:
    """Verify delete redirects without action for published editions."""
    request = _make_request()
    edition = Edition(id="ed-1", content={}, status=EditionStatus.PUBLISHED)

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as mock_links_repo_cls,
    ):
        editions_repo = AsyncMock()
        editions_repo.get.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        mock_links_repo_cls.return_value = links_repo

        response = await delete_link(request, link_id="link-1", edition_id="ed-1")

        links_repo.soft_delete.assert_not_called()
        assert response.status_code == _EXPECTED_REDIRECT_STATUS
