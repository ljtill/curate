"""Azure OpenAI / Microsoft Foundry chat client factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential

if TYPE_CHECKING:
    from agent_stack.config import FoundryConfig

logger = logging.getLogger(__name__)


def create_chat_client(config: FoundryConfig) -> AzureOpenAIChatClient:
    """Create an AzureOpenAIChatClient authenticated via DefaultAzureCredential.

    Uses Azure CLI credentials in local development and managed identity
    in deployed environments.
    """
    logger.info(
        "Chat client created — endpoint=%s model=%s",
        config.project_endpoint,
        config.model,
    )
    return AzureOpenAIChatClient(
        endpoint=config.project_endpoint,
        deployment_name=config.model,
        credential=DefaultAzureCredential(),
    )
