"""Centralized logging configuration for SalmAlm.

Provides a single ``setup_logging()`` entry-point that configures
format, level, and optional file output for the whole application.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

_DEFAULT_FMT = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: str = "INFO",
    fmt: Optional[str] = None,
    datefmt: Optional[str] = None,
    log_file: Optional[str | Path] = None,
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    json_format: bool = False,
) -> logging.Logger:
    """Configure the ``salmalm`` root logger.

    Parameters
    ----------
    level:
        Logging level name (``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``).
        Can also be set via ``SALMALM_LOG_LEVEL`` env var.
    fmt:
        Custom format string (ignored when *json_format* is True).
    datefmt:
        Date format string for the formatter.
    log_file:
        Path to a rotating log file.  ``None`` disables file output.
        Can also be set via ``SALMALM_LOG_FILE`` env var.
    max_bytes:
        Maximum bytes per log file before rotation.
    backup_count:
        Number of rotated backup files to keep.
    json_format:
        When True, use the structured JSON formatter from
        ``salmalm.utils.logging_ext`` (if available).

    Returns
    -------
    logging.Logger
        The configured ``salmalm`` logger.
    """
    # Resolve from env overrides
    level = os.environ.get("SALMALM_LOG_LEVEL", level).upper()
    log_file = log_file or os.environ.get("SALMALM_LOG_FILE")

    logger = logging.getLogger("salmalm")
    logger.setLevel(getattr(logging, level, logging.INFO))

    # Clear existing handlers to allow re-configuration
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Formatter
    formatter: logging.Formatter
    if json_format:
        try:
            from salmalm.utils.logging_ext import JSONFormatter

            formatter = JSONFormatter()
        except Exception as e:  # noqa: broad-except
            formatter = logging.Formatter(fmt or _DEFAULT_FMT, datefmt=datefmt or _DEFAULT_DATEFMT)
    else:
        formatter = logging.Formatter(fmt or _DEFAULT_FMT, datefmt=datefmt or _DEFAULT_DATEFMT)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
