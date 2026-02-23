"""Tests for PublishAgent tool methods."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from curate_common.models.edition import Edition, EditionStatus
from curate_worker.agents.publish import PublishAgent


@pytest.fixture
def editions_repo() -> AsyncMock:
    """Create a editions repo for testing."""
    return AsyncMock()


@pytest.fixture
def publish_agent(
    editions_repo: AsyncMock,
) -> tuple[PublishAgent, object, object, object]:
    """Create a publish agent for testing."""
    client = MagicMock()
    with patch("curate_worker.agents.publish.Agent"):
        return PublishAgent(
            client, editions_repo, render_fn=AsyncMock(), upload_fn=AsyncMock()
        )


@pytest.fixture
def publish_agent_no_fns(editions_repo: AsyncMock) -> tuple[PublishAgent, object]:
    """Create a publish agent no fns for testing."""
    client = MagicMock()
    with patch("curate_worker.agents.publish.Agent"):
        return PublishAgent(client, editions_repo)


async def test_render_and_upload_calls_functions(
    publish_agent: PublishAgent, editions_repo: AsyncMock
) -> None:
    """Verify render and upload calls functions."""
    edition = Edition(id="ed-1", content={"title": "Test"})
    editions_repo.get.return_value = edition
    publish_agent.render_fn.return_value = "<html>test</html>"

    result = json.loads(await publish_agent.render_and_upload("ed-1"))

    assert result["status"] == "uploaded"
    publish_agent.render_fn.assert_called_once_with(edition)
    publish_agent.upload_fn.assert_called_once_with("ed-1", "<html>test</html>")


async def test_render_and_upload_skips_without_functions(
    publish_agent_no_fns: PublishAgent, editions_repo: AsyncMock
) -> None:
    """Verify render and upload skips without functions."""
    edition = Edition(id="ed-1", content={"title": "Test"})
    editions_repo.get.return_value = edition

    result = json.loads(await publish_agent_no_fns.render_and_upload("ed-1"))
    assert result["status"] == "skipped"


async def test_render_and_upload_edition_not_found(
    publish_agent: PublishAgent, editions_repo: AsyncMock
) -> None:
    """Verify render and upload edition not found."""
    editions_repo.get.return_value = None
    result = json.loads(await publish_agent.render_and_upload("missing"))
    assert "error" in result


async def test_mark_published_updates_status(
    publish_agent: PublishAgent, editions_repo: AsyncMock
) -> None:
    """Verify mark published updates status."""
    edition = Edition(id="ed-1", content={}, status=EditionStatus.IN_REVIEW)
    editions_repo.get.return_value = edition

    result = json.loads(await publish_agent.mark_published("ed-1"))

    assert result["status"] == "published"
    assert edition.status == EditionStatus.PUBLISHED
    assert edition.published_at is not None
    editions_repo.update.assert_called_once()


async def test_mark_published_edition_not_found(
    publish_agent: PublishAgent, editions_repo: AsyncMock
) -> None:
    """Verify mark published edition not found."""
    editions_repo.get.return_value = None
    result = json.loads(await publish_agent.mark_published("missing"))
    assert "error" in result
