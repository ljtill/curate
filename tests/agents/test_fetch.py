"""Tests for FetchAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent_stack.agents.fetch import FetchAgent
from agent_stack.models.link import Link, LinkStatus


@pytest.fixture
def links_repo():
    return AsyncMock()


@pytest.fixture
def fetch_agent(links_repo):
    client = MagicMock()
    with patch("agent_stack.agents.fetch.Agent"):
        return FetchAgent(client, links_repo)


@pytest.mark.asyncio
async def test_save_fetched_content_updates_link(fetch_agent, links_repo):
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1")
    links_repo.get.return_value = link

    result = json.loads(await fetch_agent._save_fetched_content("link-1", "ed-1", "My Title", "Page content"))

    assert result["status"] == "saved"
    assert link.title == "My Title"
    assert link.content == "Page content"
    assert link.status == LinkStatus.FETCHING
    links_repo.update.assert_called_once_with(link, "ed-1")


@pytest.mark.asyncio
async def test_save_fetched_content_link_not_found(fetch_agent, links_repo):
    links_repo.get.return_value = None

    result = json.loads(await fetch_agent._save_fetched_content("missing", "ed-1", "Title", "Content"))

    assert "error" in result
    links_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_url_returns_error_on_connect_error():
    with patch("agent_stack.agents.fetch.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = json.loads(await FetchAgent._fetch_url.func("http://unreachable.invalid"))

        assert result["unreachable"] is True
        assert "error" in result


@pytest.mark.asyncio
async def test_fetch_url_returns_error_on_http_status_error():
    with patch("agent_stack.agents.fetch.httpx.AsyncClient") as MockClient:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = json.loads(await FetchAgent._fetch_url.func("https://example.com/missing"))

        assert result["unreachable"] is True
        assert "404" in result["error"]
