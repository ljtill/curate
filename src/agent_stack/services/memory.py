"""Memory service — initialization and management of Foundry Memory stores.

Provides the business-logic layer consumed by both the pipeline (agent wiring)
and the Settings dashboard routes for listing, searching, and clearing memories.
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from azure.core.exceptions import HttpResponseError

if TYPE_CHECKING:
    from azure.ai.projects import AIProjectClient

    from agent_stack.config import FoundryMemoryConfig

logger = logging.getLogger(__name__)


class MemoryService:
    """Manage Foundry Memory stores — initialization, querying, and clearing."""

    def __init__(
        self,
        project_client: AIProjectClient,
        config: FoundryMemoryConfig,
    ) -> None:
        """Initialize the service.

        Args:
            project_client: Authenticated Foundry project client.
            config: Memory configuration settings.

        """
        self._client = project_client
        self._config = config
        self._enabled = config.enabled

    # -- Initialization ----------------------------------------------------

    async def ensure_memory_store(self) -> None:
        """Create the memory store if it doesn't already exist."""
        if not self._enabled:
            logger.info("Foundry Memory is disabled, skipping store creation")
            return

        try:
            from azure.ai.projects.models import (  # noqa: PLC0415
                MemoryStoreDefaultDefinition,
                MemoryStoreDefaultOptions,
            )

            options = MemoryStoreDefaultOptions(
                chat_summary_enabled=True,
                user_profile_enabled=True,
                user_profile_details=(
                    "Editorial tone preferences, structural patterns, "
                    "content style guidance, feedback themes, writing voice. "
                    "Avoid raw article content, URLs, and token counts."
                ),
            )
            definition = MemoryStoreDefaultDefinition(
                chat_model=self._config.chat_model,
                embedding_model=self._config.embedding_model,
                options=options,
            )
            self._client.memory_stores.create(
                name=self._config.memory_store_name,
                definition=definition,
                description="Editorial memory store for The Agent Stack pipeline",
            )
            logger.info(
                "Foundry Memory store '%s' ensured",
                self._config.memory_store_name,
            )
        except HttpResponseError as exc:
            already_exists = (
                exc.status_code == HTTPStatus.BAD_REQUEST
                and "already exists" in (exc.message or "")
            )
            if already_exists:
                logger.info(
                    "Foundry Memory store '%s' ensured",
                    self._config.memory_store_name,
                )
            else:
                logger.warning(
                    "Failed to ensure Foundry Memory store '%s'",
                    self._config.memory_store_name,
                    exc_info=True,
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to ensure Foundry Memory store '%s'",
                self._config.memory_store_name,
                exc_info=True,
            )

    # -- Query / Search ----------------------------------------------------

    async def list_memories(self, scope: str) -> list[dict[str, Any]]:
        """List all memories for a scope (for Settings UI).

        Returns static (user-profile) memories by calling search without items.
        """
        if not self._enabled:
            return []

        try:
            from azure.ai.projects.models import MemorySearchOptions  # noqa: PLC0415

            response = self._client.memory_stores.search_memories(
                name=self._config.memory_store_name,
                scope=scope,
                options=MemorySearchOptions(max_memories=50),
            )
            return [
                {
                    "memory_id": m.memory_item.memory_id,
                    "content": m.memory_item.content,
                }
                for m in response.memories
                if m.memory_item
            ]
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to list memories (scope=%s)",
                scope,
                exc_info=True,
            )
            return []

    async def search_memories(
        self,
        scope: str,
        query: str,
        *,
        max_memories: int = 10,
    ) -> list[dict[str, Any]]:
        """Search memories by a natural-language query."""
        if not self._enabled:
            return []

        try:
            from azure.ai.projects.models import (  # noqa: PLC0415
                MemorySearchOptions,
                ResponsesUserMessageItemParam,
            )

            response = self._client.memory_stores.search_memories(
                name=self._config.memory_store_name,
                scope=scope,
                items=[ResponsesUserMessageItemParam(content=query)],
                options=MemorySearchOptions(max_memories=max_memories),
            )
            return [
                {
                    "memory_id": m.memory_item.memory_id,
                    "content": m.memory_item.content,
                }
                for m in response.memories
                if m.memory_item
            ]
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to search memories (scope=%s)",
                scope,
                exc_info=True,
            )
            return []

    # -- Clearing ----------------------------------------------------------

    async def clear_memories(self, scope: str) -> bool:
        """Clear all memories for a scope (project-wide or per-user).

        Returns True on success, False on failure.
        """
        if not self._enabled:
            return False

        try:
            self._client.memory_stores.delete_scope(
                name=self._config.memory_store_name,
                scope=scope,
            )
            logger.info("Cleared memories for scope=%s", scope)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to clear memories (scope=%s)",
                scope,
                exc_info=True,
            )
            return False
        else:
            return True

    # -- Toggle / Status ---------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Whether memory is globally enabled."""
        return self._enabled

    def set_enabled(self, *, enabled: bool) -> None:
        """Toggle memory on/off globally at runtime."""
        self._enabled = enabled
        logger.info("Foundry Memory %s", "enabled" if enabled else "disabled")

    @property
    def store_name(self) -> str:
        """Return the configured memory store name."""
        return self._config.memory_store_name
