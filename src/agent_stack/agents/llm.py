"""Azure OpenAI / Microsoft Foundry chat client factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

if TYPE_CHECKING:
    from agent_stack.config import OpenAIConfig


def create_chat_client(config: OpenAIConfig) -> AzureOpenAIChatClient:
    """Create an AzureOpenAIChatClient authenticated via DefaultAzureCredential.

    Uses Azure CLI credentials in local development and managed identity
    in deployed environments.
    """
    return AzureOpenAIChatClient(
        endpoint=config.endpoint,
        deployment_name=config.deployment,
        credential=DefaultAzureCredential(),
    )
