"""
logging_config.py — TubeWise Logging Configuration
=====================================================
Sets up structured logging with two outputs:
  1. Console (stderr): Clean emoji-rich messages for the user (INFO level)
  2. File (~/.tubewise/tubewise.log): Detailed debug logs with timestamps

USAGE:
    from logging_config import setup_logging
    setup_logging()  # Call once at startup in agent.py

    # Then in each module:
    import logging
    logger = logging.getLogger("tubewise.module_name")
    logger.info("User-facing message")
    logger.debug("Internal debug detail")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path


# Directory for TubeWise runtime files (logs, queue DB, etc.)
TUBEWISE_DIR = Path.home() / ".tubewise"

# Default log file path
DEFAULT_LOG_FILE = TUBEWISE_DIR / "tubewise.log"


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """
    Configure logging for the entire TubeWise application.

    Two handlers are created:
      - Console handler: Shows clean messages to the user on stderr.
        Uses a bare %(message)s format so emoji-rich output looks the same
        as the old print() calls.
      - File handler: Writes detailed debug logs with timestamps to a file.
        Useful for troubleshooting without cluttering the console.

    Args:
        level:    Logging level for console output ("DEBUG", "INFO", "WARNING", etc.)
        log_file: Path to the log file. Defaults to ~/.tubewise/tubewise.log
    """
    # Ensure ~/.tubewise/ directory exists
    TUBEWISE_DIR.mkdir(parents=True, exist_ok=True)

    log_path = log_file or str(DEFAULT_LOG_FILE)

    # Get the root TubeWise logger — all module loggers inherit from this
    root_logger = logging.getLogger("tubewise")
    root_logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter

    # Prevent duplicate handlers if setup_logging is called multiple times
    if root_logger.handlers:
        return

    # ── Console handler: user-facing output ──
    console_handler = logging.StreamHandler()  # Defaults to stderr
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(console_handler)

    # ── File handler: debug logs with timestamps ──
    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        root_logger.addHandler(file_handler)
    except (OSError, PermissionError):
        # If we can't write to the log file, continue without file logging
        root_logger.warning(f"Could not create log file at {log_path}")
