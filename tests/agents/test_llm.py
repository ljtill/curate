"""Tests for the LLM client factory."""

from unittest.mock import patch

from agent_stack.agents.llm import create_chat_client
from agent_stack.config import FoundryConfig


class TestCreateChatClient:
    """Test the Create Chat Client."""

    def test_creates_client_with_default_credential(
        self, foundry_config: FoundryConfig
    ) -> None:
        """Verify creates client with DefaultAzureCredential."""
        with (
            patch("agent_stack.agents.llm.AzureOpenAIChatClient") as mock_client_cls,
            patch("agent_stack.agents.llm.DefaultAzureCredential") as mock_cred_cls,
        ):
            client = create_chat_client(foundry_config)

            mock_client_cls.assert_called_once_with(
                endpoint=foundry_config.project_endpoint,
                deployment_name=foundry_config.model,
                credential=mock_cred_cls.return_value,
            )
            assert client == mock_client_cls.return_value
