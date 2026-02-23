"""Worker entry point — runs the agent pipeline change feed processor."""

from __future__ import annotations

import asyncio
import logging
import signal

from curate_common.config import load_settings
from curate_common.database.repositories.editions import EditionRepository
from curate_common.health import check_emulators
from curate_common.logging import configure_logging
from curate_worker.startup import (
    init_chat_client,
    init_database,
    init_memory,
    init_pipeline,
    init_storage,
)

logger = logging.getLogger(__name__)


async def run() -> None:
    """Initialize and run the worker until terminated."""
    settings = load_settings()
    configure_logging(settings.app.log_level, log_file="worker.log")

    logger.info("Worker starting")

    if settings.app.is_development and not await check_emulators(settings):
        return

    try:
        cosmos = await init_database(settings)
    except ConnectionError as exc:
        logger.error(str(exc))  # noqa: TRY400
        return
    chat_client = init_chat_client(settings)
    if chat_client is None:
        logger.error("Cannot start worker without a configured LLM provider")
        await cosmos.close()
        return

    editions_repo = EditionRepository(cosmos.database)
    storage, renderer = await init_storage(settings, editions_repo)
    context_providers = await init_memory(settings)

    # Import here to allow the event bridge to be swapped
    from curate_worker.events import ServiceBusPublisher  # noqa: PLC0415

    event_publisher = ServiceBusPublisher(settings.servicebus)

    processor = await init_pipeline(
        chat_client,
        cosmos,
        editions_repo,
        event_publisher=event_publisher,
        render_fn=renderer.render_edition,
        upload_fn=storage.upload_html,
        context_providers=context_providers,
    )

    logger.info("Worker running")

    # Wait until terminated
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()

    logger.info("Worker shutting down")
    await processor.stop()
    await storage.close()
    await cosmos.close()
    logger.info("Worker shutdown complete")


def main() -> None:
    """Entry point for the worker process."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
