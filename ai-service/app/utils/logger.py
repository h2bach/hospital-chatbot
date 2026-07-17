"""
Structured logging setup.

Outputs JSON logs to stdout so they are easy to search in Docker logs,
CloudWatch, GCP Logging, etc.
"""

import logging
import sys

from pythonjsonlogger import json as json_log


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with JSON output on stdout."""

    handler = logging.StreamHandler(sys.stdout)

    formatter = json_log.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers = [handler]

    # Reduce noise from third-party libraries
    for noisy in ("uvicorn.access", "httpcore", "openai", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
