"""Centralized logging module for the Customer Analytics Platform."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from src.config.paths import LOGS_DIR
from src.config.settings import settings


def setup_logger(
    name: str = "customer_analytics",
    log_level: Optional[str] = None,
    log_to_file: Optional[bool] = None,
    log_file_path: Optional[Path] = None,
) -> logging.Logger:
    """Configure and return a standardized logger instance.

    Args:
        name: Name of the logger (typically module name: `__name__`).
        log_level: Optional log level override (e.g. "DEBUG", "INFO", "WARNING").
        log_to_file: Whether to write logs to a file in addition to console.
        log_file_path: Custom destination file path for logs.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Resolve configuration options
    level_str = (log_level or settings.logging.level).upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers if the logger has already been configured
    if logger.hasHandlers():
        return logger

    # Standard formatter
    formatter = logging.Formatter(settings.logging.format)

    # 1. Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. File handler (if enabled)
    should_log_to_file = (
        log_to_file if log_to_file is not None else settings.logging.file_logging
    )
    if should_log_to_file:
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            target_log_file = log_file_path or (LOGS_DIR / settings.logging.file_name)

            # Rotating file handler (max 10MB per file, keeping up to 3 backups)
            file_handler = RotatingFileHandler(
                filename=str(target_log_file),
                maxBytes=10 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except (OSError, PermissionError) as err:
            logger.warning("Could not initialize file logging handler: %s", err)

    # Prevent logs from propagating to root logger and duplicating output
    logger.propagate = False

    return logger


def get_logger(name: str = "customer_analytics") -> logging.Logger:
    """Retrieve an existing logger or initialize a new one with standard settings.

    Usage:
        from src.utils import get_logger
        logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        return setup_logger(name)
    return logger
