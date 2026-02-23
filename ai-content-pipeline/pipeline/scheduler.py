"""
Phase 5: Blotato-based social media scheduling and posting.
"""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from config import Config
from utils.file_manager import FileManager

logger = logging.getLogger("pipeline.scheduler")


class BlatoScheduler:
    """Schedules and publishes content via the Blotato API."""

    def __init__(self) -> None:
        self.base_url = Config.BLOTATO_BASE_URL
        self.api_key = Config.BLOTATO_API_KEY
        if not self.api_key:
            logger.warning("BLOTATO_API_KEY not set — scheduling will be skipped")

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
        }

    # ── Media upload ─────────────────────────────────────────────────────

    def upload_media(self, file_path: str) -> str | None:
        """Upload a video file to Blotato.

        Returns the media_id on success.
        """
        if not self.api_key:
            logger.error("Cannot upload: BLOTATO_API_KEY not set")
            return None

        url = f"{self.base_url}/v2/media/upload"

        try:
            with open(file_path, "rb") as f:
                files = {"file": (Path(file_path).name, f, "video/mp4")}
                resp = requests.post(
                    url,
                    headers=self._headers(),
                    files=files,
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
                media_id = data.get("media_id", data.get("id", ""))
                if media_id:
                    logger.info("Uploaded media: %s -> %s", file_path, media_id)
                    return media_id
                logger.error("No media_id in upload response: %s", data)
                return None

        except Exception as exc:
            logger.error("Media upload failed for %s: %s", file_path, exc)
            return None

    # ── Post scheduling ──────────────────────────────────────────────────

    def schedule_post(
        self,
        media_id: str,
        caption: str,
        platforms: list[str],
        schedule_time: str | None = None,
    ) -> str | None:
        """Schedule a post on one or more platforms.

        Returns the post_submission_id on success.
        """
        if not self.api_key:
            logger.error("Cannot schedule: BLOTATO_API_KEY not set")
            return None

        url = f"{self.base_url}/v2/posts"
        body: dict[str, Any] = {
            "platforms": platforms,
            "media_ids": [media_id],
            "caption": caption,
        }

        if schedule_time:
            body["schedule_time"] = schedule_time
        else:
            body["schedule"] = "next_free_slot"

        try:
            resp = requests.post(
                url,
                headers={**self._headers(), "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            submission_id = data.get("post_submission_id", data.get("id", ""))
            if submission_id:
                logger.info("Post scheduled: %s on %s", submission_id, platforms)
                return submission_id
            logger.error("No submission_id in response: %s", data)
            return None

        except Exception as exc:
            logger.error("Post scheduling failed: %s", exc)
            return None

    # ── Status check ─────────────────────────────────────────────────────

    def get_post_status(self, post_submission_id: str) -> dict[str, Any]:
        """Check the status of a scheduled post."""
        if not self.api_key:
            return {"error": "BLOTATO_API_KEY not set"}

        url = f"{self.base_url}/v2/posts/{post_submission_id}"
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("Status check failed for %s: %s", post_submission_id, exc)
            return {"error": str(exc)}

    # ── Batch scheduling ─────────────────────────────────────────────────

    def schedule_batch(
        self,
        videos_with_captions: list[dict[str, str]],
        platforms: list[str],
    ) -> list[str]:
        """Upload and schedule a batch of videos spread across the next 7 days.

        Each dict must have keys: video_path, caption.
        Returns a list of submission IDs for successfully scheduled posts.
        """
        if not self.api_key:
            logger.error("Cannot schedule batch: BLOTATO_API_KEY not set")
            return []

        submission_ids: list[str] = []
        total = len(videos_with_captions)
        posts_per_day = Config.POSTS_PER_DAY

        # Spread posts across 7 days
        total_slots = 7 * posts_per_day
        now = datetime.now(timezone.utc)

        for i, item in enumerate(videos_with_captions):
            video_path = item.get("video_path", "")
            caption = item.get("caption", "")

            if not video_path or not Path(video_path).exists():
                logger.warning("Skipping missing video: %s", video_path)
                continue

            # Calculate schedule time
            day_offset = i // posts_per_day
            slot_in_day = i % posts_per_day
            # Space posts at 9am, 1pm, 6pm
            hours = [9, 13, 18]
            hour = hours[slot_in_day % len(hours)]
            schedule_dt = now + timedelta(days=day_offset + 1)
            schedule_dt = schedule_dt.replace(hour=hour, minute=0, second=0, microsecond=0)
            schedule_time = schedule_dt.isoformat()

            logger.info(
                "Scheduling %d/%d for %s", i + 1, total, schedule_time
            )

            # Upload
            media_id = self.upload_media(video_path)
            if not media_id:
                continue

            # Schedule
            sub_id = self.schedule_post(media_id, caption, platforms, schedule_time)
            if sub_id:
                submission_ids.append(sub_id)

        logger.info(
            "Batch scheduling complete: %d/%d scheduled", len(submission_ids), total
        )
        return submission_ids
