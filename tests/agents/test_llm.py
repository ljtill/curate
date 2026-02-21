"""Tests for the LLM client factory."""

from unittest.mock import patch

import pytest

from agent_stack.agents.llm import create_chat_client
from agent_stack.config import OpenAIConfig


@pytest.mark.unit
class TestCreateChatClient:
    """Test the Create Chat Client."""

    def test_creates_client_with_api_key(self, openai_config: OpenAIConfig) -> None:
        """Verify creates client with api key."""
        with patch("agent_stack.agents.llm.AzureOpenAIChatClient") as mock_client_cls:
            client = create_chat_client(openai_config, use_key="test-api-key")

            mock_client_cls.assert_called_once_with(
                endpoint=openai_config.endpoint,
                deployment_name=openai_config.deployment,
                api_key="test-api-key",
            )
            assert client == mock_client_cls.return_value

    def test_creates_client_with_managed_identity(
        self, openai_config: OpenAIConfig
    ) -> None:
        """Verify creates client with managed identity."""
        with (
            patch("agent_stack.agents.llm.AzureOpenAIChatClient") as mock_client_cls,
            patch("agent_stack.agents.llm.DefaultAzureCredential") as mock_cred_cls,
        ):
            client = create_chat_client(openai_config)

            mock_client_cls.assert_called_once_with(
                endpoint=openai_config.endpoint,
                deployment_name=openai_config.deployment,
                credential=mock_cred_cls.return_value,
            )
            assert client == mock_client_cls.return_value
