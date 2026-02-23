"""
Configuration module — loads all environment variables and pipeline settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)


class Config:
    """Centralised configuration loaded from environment variables."""

    # ── Paths ────────────────────────────────────────────────────────────
    BASE_DIR: Path = Path(__file__).resolve().parent
    OUTPUTS_DIR: Path = BASE_DIR / "outputs"
    VIDEOS_DIR: Path = OUTPUTS_DIR / "videos"
    AUDIO_DIR: Path = OUTPUTS_DIR / "audio"
    FINAL_DIR: Path = OUTPUTS_DIR / "final"
    LOGS_DIR: Path = OUTPUTS_DIR / "logs"
    SOUL_ID_DIR: Path = BASE_DIR / "soul_id"
    PHOTOS_DIR: Path = SOUL_ID_DIR / "photos"
    VOICE_SAMPLES_DIR: Path = SOUL_ID_DIR / "voice_samples"
    DB_PATH: Path = OUTPUTS_DIR / "pipeline.db"

    # ── API Keys ─────────────────────────────────────────────────────────
    APIFY_API_TOKEN: str = os.getenv("APIFY_API_TOKEN", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    HIGGSFIELD_API_KEY: str = os.getenv("HIGGSFIELD_API_KEY", "")
    HIGGSFIELD_API_SECRET: str = os.getenv("HIGGSFIELD_API_SECRET", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    BLOTATO_API_KEY: str = os.getenv("BLOTATO_API_KEY", "")

    # ── Pipeline Settings ────────────────────────────────────────────────
    SOUL_ID: str = os.getenv("SOUL_ID", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")
    POSTS_PER_DAY: int = int(os.getenv("POSTS_PER_DAY", "3"))
    PLATFORMS: list[str] = os.getenv("PLATFORMS", "tiktok,instagram,youtube").split(",")
    APPROVAL_MODE: str = os.getenv("APPROVAL_MODE", "auto")

    # ── Higgsfield ───────────────────────────────────────────────────────
    HIGGSFIELD_BASE_URL: str = "https://api.higgsfield.ai"

    # ── Blotato ──────────────────────────────────────────────────────────
    BLOTATO_BASE_URL: str = "https://api.blotato.com"

    @classmethod
    def ensure_dirs(cls) -> None:
        """Create all required output directories if they don't exist."""
        for d in (
            cls.OUTPUTS_DIR,
            cls.VIDEOS_DIR,
            cls.AUDIO_DIR,
            cls.FINAL_DIR,
            cls.LOGS_DIR,
            cls.SOUL_ID_DIR,
            cls.PHOTOS_DIR,
            cls.VOICE_SAMPLES_DIR,
        ):
            d.mkdir(parents=True, exist_ok=True)

    @classmethod
    def update_env(cls, key: str, value: str) -> None:
        """Write or update a key in the .env file."""
        env_path = cls.BASE_DIR / ".env"
        lines: list[str] = []
        found = False

        if env_path.exists():
            with open(env_path) as f:
                lines = f.readlines()

        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key}={value}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        # Also update the live config attribute
        setattr(cls, key, value)
