"""
Centralized structured logging configuration.

Usage:
    from utils.logging import setup_logging, get_logger

    setup_logging()  # call once at startup
    logger = get_logger(__name__)
    logger.info("something happened", key="value", count=42)

Output formats:
    LOG_FORMAT=console  → colored human-readable (dev)
    LOG_FORMAT=json     → JSON lines (production)
"""
import logging
import sys

import structlog

from config import settings


def setup_logging() -> None:
    """Configure structlog + stdlib logging integration.

    Call this once at application startup (run_collectors.py, api/main.py, etc).
    """
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    is_json = settings.log_format.lower() == "json"

    # Shared processors for both structlog and stdlib
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if is_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    # Configure structlog — use stdlib LoggerFactory so it integrates
    # with Python's logging and third-party libraries see the same format
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Single handler for all stdlib loggers (structlog routes through here too)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    ))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

    # Quiet noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("web3").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger bound to the given name."""
    return structlog.get_logger(name)
