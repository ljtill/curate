"""Azure OpenAI / Microsoft Foundry chat client factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

if TYPE_CHECKING:
    from agent_stack.config import OpenAIConfig


def create_chat_client(
    config: OpenAIConfig, *, use_key: str | None = None
) -> AzureOpenAIChatClient:
    """Create an AzureOpenAIChatClient authenticated via managed identity or API key.

    In local development, pass ``use_key`` to authenticate with an API key.
    In deployed environments, ``DefaultAzureCredential`` is used automatically.
    """
    if use_key:
        return AzureOpenAIChatClient(
            endpoint=config.endpoint,
            deployment_name=config.deployment,
            api_key=use_key,
        )

    return AzureOpenAIChatClient(
        endpoint=config.endpoint,
        deployment_name=config.deployment,
        credential=DefaultAzureCredential(),
    )
