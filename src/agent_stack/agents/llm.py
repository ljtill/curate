"""Microsoft Foundry chat client factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import DefaultAzureCredential

if TYPE_CHECKING:
    from agent_framework import BaseChatClient

    from agent_stack.config import FoundryConfig

logger = logging.getLogger(__name__)


def create_chat_client(config: FoundryConfig) -> BaseChatClient:
    """Create a chat client for the configured Foundry provider.

    When ``config.is_local`` is True, starts Microsoft Foundry Local via the
    ``foundry-local-sdk`` and returns an ``OpenAIChatClient`` pointed at the
    local service.  Otherwise, returns an ``AzureOpenAIResponsesClient``
    connected via the Foundry project endpoint.
    """
    if config.is_local:
        return _create_local_client(config)

    logger.info(
        "Chat client created — provider=cloud endpoint=%s model=%s",
        config.project_endpoint,
        config.model,
    )
    return AzureOpenAIResponsesClient(
        project_endpoint=config.project_endpoint,
        deployment_name=config.model,
        credential=DefaultAzureCredential(),
    )


def _create_local_client(config: FoundryConfig) -> BaseChatClient:
    """Create a chat client backed by Microsoft Foundry Local."""
    from agent_framework.openai import OpenAIChatClient  # noqa: PLC0415
    from foundry_local import FoundryLocalManager  # noqa: PLC0415

    manager = FoundryLocalManager(config.local_model)
    model_info = manager.get_model_info(config.local_model)
    if model_info is None:
        msg = f"Model '{config.local_model}' not found in Foundry Local catalog"
        raise RuntimeError(msg)

    logger.info(
        "Chat client created — provider=local model=%s endpoint=%s",
        model_info.id,
        manager.endpoint,
    )
    return OpenAIChatClient(
        base_url=manager.endpoint,
        model_id=model_info.id,
        api_key=manager.api_key,
    )
