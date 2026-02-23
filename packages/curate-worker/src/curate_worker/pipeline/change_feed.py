"""Cosmos DB change feed processor.

Listens for document changes and delegates to the orchestrator.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from azure.core.exceptions import ResourceNotFoundError, ServiceResponseError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from azure.cosmos.aio import ContainerProxy, DatabaseProxy

    from curate_worker.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)
_MAX_CONCURRENT_HANDLERS = 25


class ChangeFeedProcessor:
    """Consumes Cosmos DB change feed for links and feedback containers.

    Runs as a background task within the FastAPI lifespan. Handlers are
    dispatched as background tasks so the poll loop stays responsive and
    does not block the event loop during long-running agent processing.
    """

    def __init__(
        self, database: DatabaseProxy, orchestrator: PipelineOrchestrator
    ) -> None:
        """Initialize the change feed processor with database and orchestrator."""
        self._database = database
        self._orchestrator = orchestrator
        self._running = False
        self._task: asyncio.Task | None = None
        self._handler_tasks: set[asyncio.Task] = set()
        self._handler_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_HANDLERS)
        self._metadata: ContainerProxy | None = None

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
        self._metadata = self._database.get_container_client("metadata")
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
        for task in list(self._handler_tasks):
            task.cancel()
        if self._handler_tasks:
            await asyncio.gather(*self._handler_tasks, return_exceptions=True)
            self._handler_tasks.clear()
        logger.info("Change feed processor stopped")

    async def _load_token(self, container_name: str) -> str | None:
        """Load a persisted continuation token from the metadata container."""
        if not self._metadata:
            return None
        doc_id = f"change-feed-token-{container_name}"
        try:
            doc = await self._metadata.read_item(doc_id, partition_key=doc_id)
            return doc.get("token")
        except ResourceNotFoundError:
            return None
        except Exception:  # noqa: BLE001
            logger.warning("Failed to load continuation token for %s", container_name)
            return None

    async def _save_token(self, container_name: str, token: str | None) -> None:
        """Persist a continuation token to the metadata container."""
        if not self._metadata or not token:
            return
        doc_id = f"change-feed-token-{container_name}"
        try:
            await self._metadata.upsert_item(
                {"id": doc_id, "token": token, "container": container_name}
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to save continuation token for %s", container_name)

    async def _poll_loop(self) -> None:
        """Continuously poll change feeds for links and feedback."""
        links_container: ContainerProxy = self._database.get_container_client("links")
        feedback_container: ContainerProxy = self._database.get_container_client(
            "feedback"
        )

        links_token = await self._load_token("links")
        feedback_token = await self._load_token("feedback")

        consecutive_errors = 0

        while self._running:
            had_error = False

            try:
                links_token = await self.process_feed(
                    links_container, links_token, self._orchestrator.handle_link_change
                )
                await self._save_token("links", links_token)
            except Exception as exc:
                had_error = True
                if consecutive_errors == 0:
                    logger.exception("Error processing links change feed")
                else:
                    logger.warning("Error processing links change feed: %s", exc)

            try:
                feedback_token = await self.process_feed(
                    feedback_container,
                    feedback_token,
                    self._orchestrator.handle_feedback_change,
                )
                await self._save_token("feedback", feedback_token)
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

    async def _safe_handle(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        item: dict[str, Any],
        item_id: str,
    ) -> None:
        """Run a handler in a background task with error logging."""
        try:
            async with self._handler_semaphore:
                await handler(item)
        except Exception:
            logger.exception("Failed to process change feed item %s", item_id)

    async def process_feed(
        self,
        container: ContainerProxy,
        continuation_token: str | None,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> str | None:
        """Read a batch of changes from a container's change feed.

        Processes them sequentially.
        """
        query_kwargs: dict[str, Any] = {"max_item_count": 100}
        if continuation_token:
            query_kwargs["continuation"] = continuation_token

        response = container.query_items_change_feed(**query_kwargs)
        page_iterator = response.by_page()

        try:
            async for page in page_iterator:
                async for item in page:
                    item_id = item.get("id", "unknown")
                    logger.debug(
                        "Change feed dispatching item=%s container=%s",
                        item_id,
                        container.id,
                    )
                    task = asyncio.create_task(
                        self._safe_handle(handler, item, item_id)
                    )
                    self._handler_tasks.add(task)
                    task.add_done_callback(self._handler_tasks.discard)
        except ServiceResponseError as exc:
            if "Expected HTTP/" in str(exc):
                return continuation_token
            raise

        return page_iterator.continuation_token or continuation_token  # type: ignore[union-attr]
