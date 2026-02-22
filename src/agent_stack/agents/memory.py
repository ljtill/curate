"""Foundry Memory context provider for persistent agent memory.

Implements the Agent Framework's BaseContextProvider interface, backed by
Azure AI Foundry's managed Memory service.  Before each agent run the
provider searches the memory store for relevant context and injects it as
additional instructions.  After each run the conversation is sent to the
memory store for automatic extraction of preferences and decisions.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_framework import BaseContextProvider

if TYPE_CHECKING:
    from agent_framework import AgentSession
    from agent_framework._sessions import SessionContext
    from agent_framework._types import SupportsAgentRun
    from azure.ai.projects import AIProjectClient


logger = logging.getLogger(__name__)


class FoundryMemoryProvider(BaseContextProvider):
    """Context provider that uses Azure AI Foundry Memory for persistent agent memory.

    Memories are scoped via the ``scope`` parameter which can represent a
    project-wide editorial voice, a per-user preference set, or per-edition
    thematic context.  The provider is controllable at runtime via the
    ``enabled`` flag and the per-run ``skip_memory_capture`` session state key.
    """

    DEFAULT_SOURCE_ID = "foundry_memory"

    def __init__(
        self,
        project_client: AIProjectClient,
        memory_store_name: str,
        scope: str,
        *,
        enabled: bool = True,
        max_memories: int = 10,
    ) -> None:
        """Initialize the provider.

        Args:
            project_client: An ``AIProjectClient`` authenticated to the Foundry project.
            memory_store_name: Name of the Foundry memory store to use.
            scope: Memory scope key (e.g. ``project-editorial``,
                ``user-{oid}``, ``edition-{id}``).
            enabled: Whether memory injection / capture is active.
            max_memories: Maximum number of memories to retrieve per search.

        """
        super().__init__(source_id=self.DEFAULT_SOURCE_ID)
        self._client = project_client
        self._store_name = memory_store_name
        self._scope = scope
        self.enabled = enabled
        self._max_memories = max_memories

    # -- Lifecycle hooks ---------------------------------------------------

    async def before_run(
        self,
        *,
        agent: SupportsAgentRun,  # noqa: ARG002
        session: AgentSession,  # noqa: ARG002
        context: SessionContext,
        state: dict[str, Any],  # noqa: ARG002
    ) -> None:
        """Search the memory store and inject relevant memories as instructions."""
        if not self.enabled:
            return

        try:
            from azure.ai.projects.models import (  # noqa: PLC0415
                MemorySearchOptions,
                ResponsesUserMessageItemParam,
            )

            # Build a query from the current input messages
            query_texts = [
                msg.text
                for msg in context.input_messages
                if hasattr(msg, "text") and msg.text
            ]
            if not query_texts:
                # Fall back to static memories (user profile) when no input
                search_response = self._client.memory_stores.search_memories(
                    name=self._store_name,
                    scope=self._scope,
                    options=MemorySearchOptions(max_memories=self._max_memories),
                )
            else:
                items = [
                    ResponsesUserMessageItemParam(content=text) for text in query_texts
                ]
                search_response = self._client.memory_stores.search_memories(
                    name=self._store_name,
                    scope=self._scope,
                    items=items,
                    options=MemorySearchOptions(max_memories=self._max_memories),
                )

            if search_response.memories:
                memory_lines = [
                    m.memory_item.content
                    for m in search_response.memories
                    if m.memory_item and m.memory_item.content
                ]
                if memory_lines:
                    instructions = (
                        "The following memories represent accumulated editorial "
                        "preferences and context from previous interactions. "
                        "Use them to inform your decisions:\n"
                        + "\n".join(f"- {line}" for line in memory_lines)
                    )
                    context.extend_instructions(self.source_id, instructions)
                    logger.debug(
                        "Injected %d memories for scope %s",
                        len(memory_lines),
                        self._scope,
                    )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to search Foundry Memory (scope=%s), continuing without memory",
                self._scope,
                exc_info=True,
            )

    async def after_run(
        self,
        *,
        agent: SupportsAgentRun,  # noqa: ARG002
        session: AgentSession,  # noqa: ARG002
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Send conversation to the memory store for extraction."""
        if not self.enabled:
            return

        # Allow per-run opt-out (e.g. feedback with "Learn from this" disabled)
        if state.get("skip_memory_capture"):
            logger.debug("Memory capture skipped for this run (scope=%s)", self._scope)
            return

        try:
            from azure.ai.projects.models import (  # noqa: PLC0415
                ResponsesAssistantMessageItemParam,
                ResponsesUserMessageItemParam,
            )

            # Build conversation items from input + response messages
            items: list = []
            for msg in context.input_messages:
                text = msg.text if hasattr(msg, "text") else ""
                if text:
                    items.append(ResponsesUserMessageItemParam(content=text))

            if context.response and context.response.messages:
                for msg in context.response.messages:
                    text = msg.text if hasattr(msg, "text") else ""
                    if text:
                        items.append(ResponsesAssistantMessageItemParam(content=text))

            if items:
                # Fire and forget — don't block the pipeline on memory indexing
                self._client.memory_stores.begin_update_memories(
                    name=self._store_name,
                    scope=self._scope,
                    items=items,
                    update_delay=0,
                )
                logger.debug(
                    "Submitted %d items for memory extraction (scope=%s)",
                    len(items),
                    self._scope,
                )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to update Foundry Memory (scope=%s), "
                "continuing without capture",
                self._scope,
                exc_info=True,
            )
