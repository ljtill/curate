"""Shared test fixtures for the agent-stack test suite."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.config import CosmosConfig, EntraConfig, OpenAIConfig, StorageConfig
from agent_stack.models.agent_run import AgentRun, AgentRunStatus, AgentStage
from agent_stack.models.edition import Edition, EditionStatus
from agent_stack.models.feedback import Feedback
from agent_stack.models.link import Link, LinkStatus

# ---------------------------------------------------------------------------
# Mock repository fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_links_repo():
    return AsyncMock()


@pytest.fixture
def mock_editions_repo():
    return AsyncMock()


@pytest.fixture
def mock_feedback_repo():
    return AsyncMock()


@pytest.fixture
def mock_agent_runs_repo():
    return AsyncMock()


# ---------------------------------------------------------------------------
# Model factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_link():
    """Factory for Link instances with sensible defaults."""

    def _make(**kwargs):
        defaults = {
            "url": "https://example.com",
            "edition_id": "ed-1",
            "status": LinkStatus.SUBMITTED,
        }
        defaults.update(kwargs)
        return Link(**defaults)

    return _make


@pytest.fixture
def make_edition():
    """Factory for Edition instances with sensible defaults."""

    def _make(**kwargs):
        defaults = {
            "content": {},
            "status": EditionStatus.CREATED,
        }
        defaults.update(kwargs)
        return Edition(**defaults)

    return _make


@pytest.fixture
def make_feedback():
    """Factory for Feedback instances with sensible defaults."""

    def _make(**kwargs):
        defaults = {
            "edition_id": "ed-1",
            "section": "intro",
            "comment": "Needs work",
        }
        defaults.update(kwargs)
        return Feedback(**defaults)

    return _make


@pytest.fixture
def make_agent_run():
    """Factory for AgentRun instances with sensible defaults."""

    def _make(**kwargs):
        defaults = {
            "stage": AgentStage.FETCH,
            "trigger_id": "link-1",
            "status": AgentRunStatus.RUNNING,
        }
        defaults.update(kwargs)
        return AgentRun(**defaults)

    return _make


# ---------------------------------------------------------------------------
# Configuration fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cosmos_config():
    return CosmosConfig(endpoint="https://localhost:8081", key="test-key", database="test-db")


@pytest.fixture
def openai_config():
    return OpenAIConfig(endpoint="https://test.openai.azure.com", deployment="gpt-test")


@pytest.fixture
def storage_config():
    return StorageConfig(connection_string="DefaultEndpointsProtocol=https;AccountName=test", container="$web")


@pytest.fixture
def entra_config():
    return EntraConfig(
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret="test-secret",
    )


# ---------------------------------------------------------------------------
# Mock Cosmos container fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cosmos_db_container():
    """A mock Cosmos DB container with standard async methods."""
    container = AsyncMock()
    container.create_item = AsyncMock()
    container.read_item = AsyncMock()
    container.replace_item = AsyncMock()
    container.query_items = MagicMock()
    return container
