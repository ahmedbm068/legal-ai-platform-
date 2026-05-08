"""Structured logging setup.

Wraps the stdlib `logging` module with `structlog` so every log line is a
JSON object with timestamp, level, logger, and arbitrary key-value context.
JSON logs are queryable in any log aggregator (CloudWatch, Loki, Datadog,
ELK) without regex parsing.

Behavior:
- In production (LOG_FORMAT=json), emit JSON.
- In dev (default), emit colorful key=value rendering for readability.

Usage:
    from backend.core.logging_config import get_logger
    log = get_logger(__name__)
    log.info("copilot.dispatch", intent="ask_case", tenant_id=1, latency_ms=420)
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog


_CONFIGURED = False


def configure_logging(level: str | int = "INFO") -> None:
    """Idempotently configure structlog + stdlib logging.

    Call this once at process startup. Safe to call multiple times — second
    call is a no-op.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_format = os.getenv("LOG_FORMAT", "console").lower()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level) if isinstance(level, str) else level
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging into structlog's renderer too.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(level if isinstance(level, int) else logging.getLevelName(level))

    _CONFIGURED = True


def get_logger(name: str | None = None) -> Any:
    """Return a bound structlog logger.

    Equivalent to ``logging.getLogger(name)`` but returns a structured
    logger that accepts arbitrary keyword fields.
    """
    if not _CONFIGURED:
        configure_logging()
    return structlog.get_logger(name)
