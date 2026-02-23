"""
File management utilities — temp files, downloads, storage paths.
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import Config

logger = logging.getLogger("pipeline.files")


class FileManager:
    """Handles file organisation, temp files, and storage."""

    @staticmethod
    def ensure_output_dirs() -> None:
        """Create all output directories."""
        Config.ensure_dirs()

    @staticmethod
    def timestamped_name(prefix: str, ext: str) -> str:
        """Generate a timestamped filename."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{ts}.{ext}"

    @staticmethod
    def save_json(data: object, directory: Path, prefix: str) -> Path:
        """Save data as a timestamped JSON file. Returns the path."""
        directory.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = directory / f"{prefix}_{ts}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.debug("Saved JSON: %s", path)
        return path

    @staticmethod
    def verify_file(path: Path, min_size: int = 1) -> bool:
        """Check that a file exists and is at least min_size bytes."""
        if not path.exists():
            logger.error("File does not exist: %s", path)
            return False
        if path.stat().st_size < min_size:
            logger.error("File too small (%d bytes): %s", path.stat().st_size, path)
            return False
        return True

    @staticmethod
    def list_files(directory: Path, extensions: tuple[str, ...] = ()) -> list[Path]:
        """List files in a directory, optionally filtered by extension."""
        if not directory.exists():
            return []
        files = [f for f in directory.iterdir() if f.is_file()]
        if extensions:
            files = [f for f in files if f.suffix.lower() in extensions]
        return sorted(files)

    @staticmethod
    def clean_dir(directory: Path) -> None:
        """Remove all files in a directory (not subdirectories)."""
        if directory.exists():
            for f in directory.iterdir():
                if f.is_file():
                    f.unlink()
            logger.info("Cleaned directory: %s", directory)
