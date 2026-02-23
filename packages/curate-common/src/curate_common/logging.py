"""Shared logging configuration for web and worker services."""

from __future__ import annotations

import logging
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


class _FeedRangeFilter(logging.Filter):
    """Suppress noisy Cosmos DB change feed 'feed_range empty' messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "'feed_range' empty" not in record.getMessage()


# Third-party loggers that are too noisy at INFO level
_QUIET_LOGGERS = (
    "azure",
    "httpx",
    "httpcore",
    "openai",
    "agent_framework",
    "asyncio",
    "sse_starlette",
    "python_multipart",
)


def configure_logging(
    log_level: str,
    *,
    log_file: str | None = None,
) -> None:
    """Configure root logger with console output and optional file handler.

    Args:
        log_level: Log level name (e.g. "INFO", "DEBUG").
        log_file: Filename within ``logs/`` directory (e.g. "web.log").
            When provided, a ``FileHandler`` is added that writes to
            ``<cwd>/logs/<log_file>``.

    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        root_logger.addHandler(stream_handler)

    if log_file:
        log_dir = Path.cwd() / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = (log_dir / log_file).resolve()
        has_file_handler = any(
            isinstance(h, logging.FileHandler)
            and Path(h.baseFilename).resolve() == log_path
            for h in root_logger.handlers
        )
        if not has_file_handler:
            file_handler = logging.FileHandler(log_path, mode="w")
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
            root_logger.addHandler(file_handler)

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Route uvicorn loggers through the root logger so file handler captures them
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # Suppress noisy Cosmos DB change feed messages
    if not any(isinstance(f, _FeedRangeFilter) for f in root_logger.filters):
        root_logger.addFilter(_FeedRangeFilter())
