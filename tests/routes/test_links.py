"""Tests for link route handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.models.edition import Edition
from agent_stack.models.link import Link, LinkStatus
from agent_stack.routes.links import list_links, retry_link, submit_link


def _make_request():
    request = MagicMock()
    request.app.state.cosmos.database = MagicMock()
    request.app.state.templates = MagicMock()
    request.app.state.templates.TemplateResponse = MagicMock(return_value="<html>")
    return request


@pytest.mark.asyncio
async def test_list_links_with_active_edition():
    request = _make_request()
    edition = Edition(id="ed-1", content={})
    links = [Link(id="link-1", url="https://example.com", edition_id="ed-1")]

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as MockLinksRepo,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get_by_edition.return_value = links
        MockLinksRepo.return_value = links_repo

        await list_links(request)

        request.app.state.templates.TemplateResponse.assert_called_once()
        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == links
        assert ctx["edition"] == edition


@pytest.mark.asyncio
async def test_list_links_without_active_edition():
    request = _make_request()

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as MockLinksRepo,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = None
        mock_get_repo.return_value = editions_repo
        MockLinksRepo.return_value = AsyncMock()

        await list_links(request)

        ctx = request.app.state.templates.TemplateResponse.call_args[0][1]
        assert ctx["links"] == []
        assert ctx["edition"] is None


@pytest.mark.asyncio
async def test_submit_link_creates_link():
    request = _make_request()
    edition = Edition(id="ed-1", content={})

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as MockLinksRepo,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        MockLinksRepo.return_value = links_repo

        response = await submit_link(request, url="https://example.com")

        links_repo.create.assert_called_once()
        created = links_repo.create.call_args[0][0]
        assert created.url == "https://example.com"
        assert created.edition_id == "ed-1"
        assert response.status_code == 303


@pytest.mark.asyncio
async def test_submit_link_redirects_when_no_edition():
    request = _make_request()

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as MockLinksRepo,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = None
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        MockLinksRepo.return_value = links_repo

        response = await submit_link(request, url="https://example.com")

        links_repo.create.assert_not_called()
        assert response.status_code == 303


@pytest.mark.asyncio
async def test_retry_link_resets_to_submitted():
    request = _make_request()
    edition = Edition(id="ed-1", content={})
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1", status=LinkStatus.FAILED)

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as MockLinksRepo,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        MockLinksRepo.return_value = links_repo

        response = await retry_link(request, link_id="link-1")

        assert link.status == LinkStatus.SUBMITTED
        assert link.title is None
        assert link.content is None
        links_repo.update.assert_called_once_with(link, "ed-1")
        assert response.status_code == 303


@pytest.mark.asyncio
async def test_retry_link_ignores_non_failed():
    request = _make_request()
    edition = Edition(id="ed-1", content={})
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1", status=LinkStatus.SUBMITTED)

    with (
        patch("agent_stack.routes.links._get_editions_repo") as mock_get_repo,
        patch("agent_stack.routes.links.LinkRepository") as MockLinksRepo,
    ):
        editions_repo = AsyncMock()
        editions_repo.get_active.return_value = edition
        mock_get_repo.return_value = editions_repo

        links_repo = AsyncMock()
        links_repo.get.return_value = link
        MockLinksRepo.return_value = links_repo

        response = await retry_link(request, link_id="link-1")

        links_repo.update.assert_not_called()
        assert response.status_code == 303
