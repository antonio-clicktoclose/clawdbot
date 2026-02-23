"""
Phase 2: Higgsfield AI video generation with Soul ID support.
"""

import logging
import time
from pathlib import Path
from typing import Any

import requests

from config import Config
from utils.file_manager import FileManager

logger = logging.getLogger("pipeline.video_generator")


class HiggsFieldGenerator:
    """Generates AI videos using the Higgsfield API."""

    def __init__(self) -> None:
        self.base_url = Config.HIGGSFIELD_BASE_URL
        self.api_key = Config.HIGGSFIELD_API_KEY
        self.api_secret = Config.HIGGSFIELD_API_SECRET
        if not self.api_key:
            logger.warning("HIGGSFIELD_API_KEY is not set — video generation will be skipped")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _poll_status(
        self,
        url: str,
        status_key: str = "status",
        done_value: str = "completed",
        interval: int = 10,
        max_polls: int = 20,
    ) -> dict[str, Any] | None:
        """Poll an endpoint until the status reaches done_value or we time out."""
        for attempt in range(max_polls):
            try:
                resp = requests.get(url, headers=self._headers(), timeout=30)
                resp.raise_for_status()
                data = resp.json()
                current = data.get(status_key, "unknown")
                logger.debug("Poll %d/%d — status: %s", attempt + 1, max_polls, current)

                if current == done_value or current == "ready":
                    return data
                if current in ("failed", "error"):
                    logger.error("Polling returned failure status: %s", data)
                    return None
            except Exception as exc:
                logger.warning("Poll request failed: %s", exc)

            time.sleep(interval)

        logger.error("Polling timed out after %d attempts", max_polls)
        return None

    # ── Soul ID ──────────────────────────────────────────────────────────

    def create_soul_id(self, photo_paths: list[Path]) -> str | None:
        """Create a Higgsfield Soul ID from reference photos.

        Requires at least 5 photos. Returns the soul_id string on success.
        """
        if not self.api_key:
            logger.error("Cannot create Soul ID: HIGGSFIELD_API_KEY not set")
            return None

        if len(photo_paths) < 5:
            logger.error("Need at least 5 photos for Soul ID, got %d", len(photo_paths))
            return None

        url = f"{self.base_url}/v1/soul-id/create"
        files = []
        for p in photo_paths[:20]:  # max 20
            files.append(("photos", (p.name, open(p, "rb"), "image/jpeg")))

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = requests.post(url, headers=headers, files=files, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            soul_id = data.get("soul_id", data.get("id", ""))

            if not soul_id:
                logger.error("No soul_id in response: %s", data)
                return None

            # Poll until ready
            poll_url = f"{self.base_url}/v1/soul-id/{soul_id}/status"
            result = self._poll_status(poll_url, interval=15, max_polls=20)
            if not result:
                logger.error("Soul ID creation timed out")
                return None

            # Save to .env
            Config.update_env("SOUL_ID", soul_id)
            logger.info("Soul ID created and saved: %s", soul_id)
            return soul_id

        except Exception as exc:
            logger.error("Soul ID creation failed: %s", exc)
            return None
        finally:
            for _, file_tuple in files:
                file_tuple[1].close()

    # ── Video generation ─────────────────────────────────────────────────

    def generate_video(
        self,
        prompt: str,
        soul_id: str,
        duration: int = 15,
        motion_intensity: float = 0.7,
    ) -> str | None:
        """Generate a single video and download it locally.

        Returns the local file path or None on failure.
        """
        if not self.api_key:
            logger.error("Cannot generate video: HIGGSFIELD_API_KEY not set")
            return None

        url = f"{self.base_url}/v1/generations"
        payload = {
            "soul_id": soul_id,
            "prompt": prompt,
            "duration": duration,
            "fps": 24,
            "motion_intensity": motion_intensity,
            "aspect_ratio": "9:16",
        }

        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            generation_id = data.get("generation_id", data.get("id", ""))

            if not generation_id:
                logger.error("No generation_id in response: %s", data)
                return None

            # Poll for completion
            poll_url = f"{self.base_url}/v1/generations/{generation_id}"
            result = self._poll_status(poll_url, interval=10, max_polls=20)
            if not result:
                logger.error("Video generation timed out for id=%s", generation_id)
                return None

            # Download the video
            video_url = result.get("video_url", result.get("output", {}).get("url", ""))
            if not video_url:
                logger.error("No video URL in completed generation: %s", result)
                return None

            output_path = Config.VIDEOS_DIR / f"{generation_id}.mp4"
            self._download_file(video_url, output_path)

            if FileManager.verify_file(output_path):
                logger.info("Video downloaded: %s", output_path)
                return str(output_path)
            return None

        except Exception as exc:
            logger.error("Video generation failed: %s", exc)
            return None

    def _download_file(self, url: str, output_path: Path) -> None:
        """Download a file from a URL."""
        resp = requests.get(url, stream=True, timeout=120)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

    def generate_batch(
        self, scripts: list[dict[str, Any]], soul_id: str
    ) -> list[str]:
        """Generate one video per script sequentially.

        Returns a list of local file paths for successfully generated videos.
        """
        paths: list[str] = []
        for i, script in enumerate(scripts):
            hook = script.get("hook", script.get("topic", "AI video"))
            logger.info("Generating video %d/%d: %s", i + 1, len(scripts), hook[:60])
            path = self.generate_video(hook, soul_id)
            if path:
                paths.append(path)
            else:
                logger.warning("Skipping failed video generation for: %s", hook[:60])
        logger.info("Generated %d/%d videos", len(paths), len(scripts))
        return paths
