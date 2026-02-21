"""Tests for DraftAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_stack.agents.draft import DraftAgent
from agent_stack.models.edition import Edition
from agent_stack.models.link import Link, LinkStatus


@pytest.fixture
def repos() -> tuple[AsyncMock, AsyncMock, object]:
    """Create mock repository instances."""
    return AsyncMock(), AsyncMock()  # links_repo, editions_repo


@pytest.fixture
def draft_agent(repos: tuple[AsyncMock, AsyncMock]) -> tuple[DraftAgent, object, object]:
    """Create a draft agent for testing."""
    links_repo, editions_repo = repos
    client = MagicMock()
    with patch("agent_stack.agents.draft.Agent"):
        return DraftAgent(client, links_repo, editions_repo)


@pytest.mark.asyncio
async def test_get_reviewed_link_returns_data(draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify get reviewed link returns data."""
    links_repo, _ = repos
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        title="Title",
        content="Body",
        review={"insights": ["a"]},
    )
    links_repo.get.return_value = link

    result = json.loads(await draft_agent.get_reviewed_link("link-1", "ed-1"))
    assert result["title"] == "Title"
    assert result["review"] == {"insights": ["a"]}


@pytest.mark.asyncio
async def test_get_edition_content(draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify get edition content."""
    _, editions_repo = repos
    edition = Edition(id="ed-1", content={"title": "Newsletter"})
    editions_repo.get.return_value = edition

    result = json.loads(await draft_agent.get_edition_content("ed-1"))
    assert result["title"] == "Newsletter"


@pytest.mark.asyncio
async def test_save_draft_updates_edition_and_link(draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify save draft updates edition and link."""
    links_repo, editions_repo = repos
    edition = Edition(id="ed-1", content={}, link_ids=[])
    editions_repo.get.return_value = edition
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1")
    links_repo.get.return_value = link

    content = json.dumps({"title": "Updated"})
    result = json.loads(await draft_agent.save_draft("ed-1", "link-1", content))

    assert result["status"] == "drafted"
    assert "link-1" in edition.link_ids
    assert link.status == LinkStatus.DRAFTED
    editions_repo.update.assert_called_once()
    links_repo.update.assert_called_once()


@pytest.mark.asyncio
async def test_save_draft_deduplicates_link_ids(draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]) -> None:
    """Verify save draft deduplicates link ids."""
    links_repo, editions_repo = repos
    edition = Edition(id="ed-1", content={}, link_ids=["link-1"])
    editions_repo.get.return_value = edition
    links_repo.get.return_value = Link(id="link-1", url="https://example.com", edition_id="ed-1")

    await draft_agent.save_draft("ed-1", "link-1", json.dumps({}))

    # link-1 should not be duplicated
    assert edition.link_ids.count("link-1") == 1
