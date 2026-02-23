"""
Structured logging — console at INFO, file at DEBUG.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path


def setup_logger(name: str = "pipeline") -> logging.Logger:
    """Return a configured logger that writes to console and a daily log file."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler — INFO
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler — DEBUG
    logs_dir = Path(__file__).resolve().parent.parent / "outputs" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(logs_dir / f"pipeline_{today}.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
