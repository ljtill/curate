"""Shared logging configuration for web and worker services."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_LOG_DATE_FORMAT = "%H:%M:%S"

# ANSI colour codes keyed by log-level number
_LEVEL_COLOURS: dict[int, str] = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class _ColourFormatter(logging.Formatter):
    """Formatter that applies ANSI colour to the level name on TTY streams."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        colour = _LEVEL_COLOURS.get(record.levelno)
        if colour:
            coloured = f"{colour}{record.levelname}{_RESET}"
            msg = msg.replace(record.levelname, coloured, 1)
        return msg


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
        # Use colour formatter only when writing to a real terminal
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            stream_handler.setFormatter(_ColourFormatter(_LOG_FORMAT, _LOG_DATE_FORMAT))
        else:
            fmt = logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT)
            stream_handler.setFormatter(fmt)
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
            file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT))
            root_logger.addHandler(file_handler)

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # The LocationCache logger emits noisy "Marking ... unavailable" warnings
    # on every connectivity failure — our own code already logs this clearly.
    logging.getLogger("azure.cosmos.LocationCache").setLevel(logging.ERROR)

    # Route uvicorn loggers through the root logger so file handler captures them
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True

    # Suppress noisy Cosmos DB change feed messages
    if not any(isinstance(f, _FeedRangeFilter) for f in root_logger.filters):
        root_logger.addFilter(_FeedRangeFilter())
