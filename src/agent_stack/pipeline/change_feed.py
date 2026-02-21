"""Cosmos DB change feed processor — listens for document changes and delegates to the orchestrator."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from azure.core.exceptions import ServiceResponseError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from azure.cosmos.aio import ContainerProxy, DatabaseProxy

    from agent_stack.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)


class ChangeFeedProcessor:
    """Consumes Cosmos DB change feed for links and feedback containers.

    Runs as a background task within the FastAPI lifespan, processing changes
    sequentially to avoid race conditions on the edition document.
    """

    def __init__(self, database: DatabaseProxy, orchestrator: PipelineOrchestrator) -> None:
        """Initialize the change feed processor with database and orchestrator."""
        self._database = database
        self._orchestrator = orchestrator
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        """Return whether the processor is running."""
        return self._running

    @property
    def task(self) -> asyncio.Task | None:
        """Return the background polling task."""
        return self._task

    @property
    def orchestrator(self) -> PipelineOrchestrator:
        """Return the pipeline orchestrator."""
        return self._orchestrator

    async def start(self) -> None:
        """Start polling the change feed in a background task."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Change feed processor started")

    async def stop(self) -> None:
        """Stop the change feed processor gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Change feed processor stopped")

    async def _poll_loop(self) -> None:
        """Continuously poll change feeds for links and feedback."""
        links_container: ContainerProxy = self._database.get_container_client("links")
        feedback_container: ContainerProxy = self._database.get_container_client("feedback")

        # Track continuation tokens per container
        links_token: str | None = None
        feedback_token: str | None = None

        consecutive_errors = 0

        while self._running:
            had_error = False

            try:
                links_token = await self.process_feed(
                    links_container, links_token, self._orchestrator.handle_link_change
                )
            except Exception as exc:
                had_error = True
                if consecutive_errors == 0:
                    logger.exception("Error processing links change feed")
                else:
                    logger.warning("Error processing links change feed: %s", exc)

            try:
                feedback_token = await self.process_feed(
                    feedback_container, feedback_token, self._orchestrator.handle_feedback_change
                )
            except Exception as exc:
                had_error = True
                if consecutive_errors == 0:
                    logger.exception("Error processing feedback change feed")
                else:
                    logger.warning("Error processing feedback change feed: %s", exc)

            if had_error:
                consecutive_errors += 1
                backoff = min(1.0 * (2**consecutive_errors), 30.0)
                await asyncio.sleep(backoff)
            else:
                consecutive_errors = 0
                await asyncio.sleep(1.0)

    async def process_feed(
        self,
        container: ContainerProxy,
        continuation_token: str | None,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> str | None:
        """Read a batch of changes from a container's change feed and process them sequentially."""
        query_kwargs: dict[str, Any] = {"max_item_count": 100}
        if continuation_token:
            query_kwargs["continuation"] = continuation_token

        response = container.query_items_change_feed(**query_kwargs)
        page_iterator = response.by_page()

        try:
            async for page in page_iterator:
                async for item in page:
                    try:
                        await handler(item)
                    except Exception:
                        logger.exception("Failed to process change feed item %s", item.get("id"))
        except ServiceResponseError as exc:
            # The Cosmos DB vnext-preview emulator returns malformed HTTP responses
            # for the change feed endpoint when there are no changes, causing aiohttp
            # to fail parsing. Treat as "no changes" and keep the current token.
            if "Expected HTTP/" in str(exc):
                logger.debug("Change feed returned no changes (emulator HTTP response)")
                return continuation_token
            raise

        # AsyncPageIterator has continuation_token at runtime; type stub is imprecise.
        return page_iterator.continuation_token or continuation_token  # type: ignore[union-attr]
