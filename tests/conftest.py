"""Shared test fixtures for the agent-stack test suite."""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_stack.config import CosmosConfig, EntraConfig, OpenAIConfig, StorageConfig
from agent_stack.models.agent_run import AgentRun, AgentRunStatus, AgentStage
from agent_stack.models.edition import Edition, EditionStatus
from agent_stack.models.feedback import Feedback
from agent_stack.models.link import Link, LinkStatus

_TEST_CLIENT_SECRET = "test-secret"  # noqa: S105

# ---------------------------------------------------------------------------
# Mock repository fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_links_repo() -> AsyncMock:
    """Create a mock links repo for testing."""
    return AsyncMock()


@pytest.fixture
def mock_editions_repo() -> AsyncMock:
    """Create a mock editions repo for testing."""
    return AsyncMock()


@pytest.fixture
def mock_feedback_repo() -> AsyncMock:
    """Create a mock feedback repo for testing."""
    return AsyncMock()


@pytest.fixture
def mock_agent_runs_repo() -> AsyncMock:
    """Create a mock agent runs repo for testing."""
    return AsyncMock()


# ---------------------------------------------------------------------------
# Model factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_link() -> Callable[..., Link]:
    """Create a Link instance with sensible defaults."""

    def _make(**kwargs: Any) -> Link:
        defaults = {
            "url": "https://example.com",
            "edition_id": "ed-1",
            "status": LinkStatus.SUBMITTED,
        }
        defaults.update(kwargs)
        return Link(**defaults)

    return _make


@pytest.fixture
def make_edition() -> Callable[..., Edition]:
    """Create an Edition instance with sensible defaults."""

    def _make(**kwargs: Any) -> Edition:
        defaults = {
            "content": {},
            "status": EditionStatus.CREATED,
        }
        defaults.update(kwargs)
        return Edition(**defaults)

    return _make


@pytest.fixture
def make_feedback() -> Callable[..., Feedback]:
    """Create a Feedback instance with sensible defaults."""

    def _make(**kwargs: Any) -> Feedback:
        defaults = {
            "edition_id": "ed-1",
            "section": "intro",
            "comment": "Needs work",
        }
        defaults.update(kwargs)
        return Feedback(**defaults)

    return _make


@pytest.fixture
def make_agent_run() -> Callable[..., AgentRun]:
    """Create an AgentRun instance with sensible defaults."""

    def _make(**kwargs: Any) -> AgentRun:
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
def cosmos_config() -> tuple[CosmosConfig, object, object]:
    """Create a cosmos config for testing."""
    return CosmosConfig(
        endpoint="https://localhost:8081", key="test-key", database="test-db"
    )


@pytest.fixture
def openai_config() -> tuple[OpenAIConfig, object]:
    """Create a openai config for testing."""
    return OpenAIConfig(endpoint="https://test.openai.azure.com", deployment="gpt-test")


@pytest.fixture
def storage_config() -> tuple[StorageConfig, object]:
    """Create a storage config for testing."""
    return StorageConfig(
        connection_string="DefaultEndpointsProtocol=https;AccountName=test",
        container="$web",
    )


@pytest.fixture
def entra_config() -> EntraConfig:
    """Create a entra config for testing."""
    return EntraConfig(
        tenant_id="test-tenant",
        client_id="test-client",
        client_secret=_TEST_CLIENT_SECRET,
    )


# ---------------------------------------------------------------------------
# Mock Cosmos container fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cosmos_db_container() -> None:
    """Create a mock Cosmos DB container with standard async methods."""
    container = AsyncMock()
    container.create_item = AsyncMock()
    container.read_item = AsyncMock()
    container.replace_item = AsyncMock()
    container.query_items = MagicMock()
    return container
