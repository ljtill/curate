"""Tests for ReviewAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_common.models.link import Link, LinkStatus
from curate_worker.agents.review import ReviewAgent

_EXPECTED_RELEVANCE_SCORE = 8


@pytest.fixture
def links_repo() -> AsyncMock:
    """Create a links repo for testing."""
    return AsyncMock()


@pytest.fixture
def review_agent(links_repo: AsyncMock) -> tuple[ReviewAgent, object]:
    """Create a review agent for testing."""
    client = MagicMock()
    with patch("curate_worker.agents.review.Agent"):
        return ReviewAgent(client, links_repo)


async def test_get_link_content_returns_json(
    review_agent: ReviewAgent, links_repo: AsyncMock
) -> None:
    """Verify get link content returns json."""
    link = Link(
        id="link-1",
        url="https://example.com",
        edition_id="ed-1",
        title="Title",
        content="Body text",
    )
    links_repo.get.return_value = link

    result = json.loads(await review_agent.get_link_content("link-1", "ed-1"))

    assert result["title"] == "Title"
    assert result["content"] == "Body text"
    assert result["url"] == "https://example.com"


async def test_get_link_content_not_found(
    review_agent: ReviewAgent, links_repo: AsyncMock
) -> None:
    """Verify get link content not found."""
    links_repo.get.return_value = None
    result = json.loads(await review_agent.get_link_content("missing", "ed-1"))
    assert "error" in result


async def test_save_review_updates_link(
    review_agent: ReviewAgent, links_repo: AsyncMock
) -> None:
    """Verify save review updates link."""
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1")
    links_repo.get.return_value = link

    insights = ["insight1", "insight2"]
    result = json.loads(
        await review_agent.save_review(
            "link-1",
            "ed-1",
            insights,
            "AI/ML",
            _EXPECTED_RELEVANCE_SCORE,
            "Highly relevant",
        )
    )

    assert result["status"] == "reviewed"
    assert link.status == LinkStatus.REVIEWED
    assert link.review["category"] == "AI/ML"
    assert link.review["relevance_score"] == _EXPECTED_RELEVANCE_SCORE
    assert link.review["insights"] == ["insight1", "insight2"]
    links_repo.update.assert_called_once()


async def test_save_review_link_not_found(
    review_agent: ReviewAgent, links_repo: AsyncMock
) -> None:
    """Verify save review link not found."""
    links_repo.get.return_value = None
    result = json.loads(
        await review_agent.save_review(
            "missing", "ed-1", "[]", "cat", 5, "justification"
        )
    )
    assert "error" in result


async def test_save_review_retries_on_failure(
    review_agent: ReviewAgent, links_repo: AsyncMock
) -> None:
    """Verify save review retries on failure."""
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1")
    links_repo.get.return_value = link
    links_repo.update.side_effect = Exception("Cosmos DB error")

    result = json.loads(
        await review_agent.save_review(
            "link-1", "ed-1", "[]", "AI/ML", _EXPECTED_RELEVANCE_SCORE, "Good"
        )
    )

    assert "error" in result
    assert review_agent.save_failures == 1


async def test_save_review_raises_after_max_retries(
    review_agent: ReviewAgent, links_repo: AsyncMock
) -> None:
    """Verify save review raises after max retries."""
    link = Link(id="link-1", url="https://example.com", edition_id="ed-1")
    links_repo.get.return_value = link
    links_repo.update.side_effect = Exception("Cosmos DB error")

    for _ in range(2):
        await review_agent.save_review(
            "link-1", "ed-1", [], "AI/ML", _EXPECTED_RELEVANCE_SCORE, "Good"
        )

    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        await review_agent.save_review(
            "link-1", "ed-1", [], "AI/ML", _EXPECTED_RELEVANCE_SCORE, "Good"
        )


@pytest.mark.usefixtures("links_repo")
async def test_save_review_resets_failures_on_run(review_agent: ReviewAgent) -> None:
    """Verify save review resets failures on run."""
    review_agent.save_failures = 2
    mock_response = MagicMock()
    mock_response.usage_details = None
    mock_response.text = "done"
    review_agent.agent.run = AsyncMock(return_value=mock_response)
    await review_agent.run(
        Link(id="link-1", url="https://example.com", edition_id="ed-1")
    )
    assert review_agent.save_failures == 0
