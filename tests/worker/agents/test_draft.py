"""Tests for DraftAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_common.models.edition import Edition
from curate_common.models.link import Link, LinkStatus
from curate_worker.agents.draft import DraftAgent


@pytest.fixture
def repos() -> tuple[AsyncMock, AsyncMock, object]:
    """Create mock repository instances."""
    return AsyncMock(), AsyncMock()


@pytest.fixture
def draft_agent(
    repos: tuple[AsyncMock, AsyncMock],
) -> tuple[DraftAgent, object, object]:
    """Create a draft agent for testing."""
    links_repo, editions_repo = repos
    client = MagicMock()
    with patch("curate_worker.agents.draft.Agent"):
        return DraftAgent(client, links_repo, editions_repo)


async def test_get_reviewed_link_returns_data(
    draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
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


async def test_get_edition_content(
    draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify get edition content."""
    _, editions_repo = repos
    edition = Edition(id="ed-1", content={"title": "Newsletter"})
    editions_repo.get.return_value = edition

    result = json.loads(await draft_agent.get_edition_content("ed-1"))
    assert result["title"] == "Newsletter"


async def test_save_draft_updates_edition_and_link(
    draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
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


async def test_save_draft_deduplicates_link_ids(
    draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify save draft deduplicates link ids."""
    links_repo, editions_repo = repos
    edition = Edition(id="ed-1", content={}, link_ids=["link-1"])
    editions_repo.get.return_value = edition
    links_repo.get.return_value = Link(
        id="link-1", url="https://example.com", edition_id="ed-1"
    )

    await draft_agent.save_draft("ed-1", "link-1", json.dumps({}))

    assert edition.link_ids.count("link-1") == 1


async def test_save_draft_invalid_content_json(
    draft_agent: DraftAgent, repos: tuple[AsyncMock, AsyncMock]
) -> None:
    """Verify save draft returns error for malformed content JSON."""
    _, editions_repo = repos

    result = json.loads(
        await draft_agent.save_draft("ed-1", "link-1", "not valid json")
    )

    assert "error" in result
    assert "JSON" in result["error"]
    editions_repo.update.assert_not_called()


_EXPECTED_RETRY_COUNT = 2


async def test_run_retries_when_save_draft_not_called(
    draft_agent: DraftAgent,
) -> None:
    """Verify run sends a follow-up message when save_draft is not called."""
    mock_response = MagicMock()
    mock_response.usage_details = None
    mock_response.text = "Here is the draft content..."

    call_count = 0

    async def fake_run(  # noqa: ANN202
        message: str,  # noqa: ARG001
        *,
        session: object = None,  # noqa: ARG001
        **kwargs: object,  # noqa: ARG001
    ):
        nonlocal call_count
        call_count += 1
        if call_count == _EXPECTED_RETRY_COUNT:
            draft_agent._draft_saved = True  # noqa: SLF001
        return mock_response

    draft_agent.agent.run = fake_run
    draft_agent.agent.create_session = MagicMock()
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1")

    await draft_agent.run(link)

    assert call_count == _EXPECTED_RETRY_COUNT
    assert draft_agent._draft_saved is True  # noqa: SLF001
