"""Tests for the LLM client factory."""

from unittest.mock import MagicMock, patch

from agent_stack.agents.llm import create_chat_client
from agent_stack.config import FoundryConfig


class TestCreateChatClient:
    """Test the Create Chat Client."""

    def test_creates_client_with_default_credential(
        self, foundry_config: FoundryConfig
    ) -> None:
        """Verify creates client with DefaultAzureCredential."""
        with (
            patch(
                "agent_stack.agents.llm.AzureOpenAIResponsesClient"
            ) as mock_client_cls,
            patch("agent_stack.agents.llm.DefaultAzureCredential") as mock_cred_cls,
        ):
            client = create_chat_client(foundry_config)

            mock_client_cls.assert_called_once_with(
                project_endpoint=foundry_config.project_endpoint,
                deployment_name=foundry_config.model,
                credential=mock_cred_cls.return_value,
            )
            assert client == mock_client_cls.return_value

    def test_creates_local_client_with_foundry_local(
        self, foundry_local_config: FoundryConfig
    ) -> None:
        """Verify creates OpenAIChatClient pointed at Foundry Local."""
        mock_manager = MagicMock()
        mock_manager.endpoint = "http://localhost:5273/v1"
        mock_manager.api_key = "local-key"
        mock_model_info = MagicMock()
        mock_model_info.id = "phi-4-mini-onnx"
        mock_manager.get_model_info.return_value = mock_model_info

        with (
            patch(
                "foundry_local.FoundryLocalManager",
                return_value=mock_manager,
            ) as mock_manager_cls,
            patch(
                "agent_framework.openai.OpenAIChatClient",
            ) as mock_client_cls,
        ):
            client = create_chat_client(foundry_local_config)

            mock_manager_cls.assert_called_once_with(foundry_local_config.local_model)
            mock_manager.get_model_info.assert_called_once_with(
                foundry_local_config.local_model
            )
            mock_client_cls.assert_called_once_with(
                base_url=mock_manager.endpoint,
                model_id=mock_model_info.id,
                api_key=mock_manager.api_key,
            )
            assert client == mock_client_cls.return_value
