"""
Pipeline orchestrator — coordinates all phases of the content pipeline.
"""

import json
import logging
import time
from typing import Any

import schedule as schedule_lib

from config import Config
from database import Database
from pipeline.scraper import ApifyScraper
from pipeline.analyzer import GeminiAnalyzer
from pipeline.video_generator import HiggsFieldGenerator
from pipeline.voice_synthesizer import ElevenLabsVoice
from pipeline.video_editor import VideoEditor
from pipeline.scheduler import BlatoScheduler
from utils.file_manager import FileManager

logger = logging.getLogger("pipeline.orchestrator")


class PipelineOrchestrator:
    """Coordinates discovery, generation, and scheduling phases."""

    def __init__(self) -> None:
        Config.ensure_dirs()
        self.db = Database()

    # ── Phase 1: Discovery ───────────────────────────────────────────────

    def run_discovery(self, count: int = 20) -> list[int]:
        """Scrape viral content, analyse with Gemini, and queue for generation.

        Returns a list of content_queue row IDs.
        """
        logger.info("=== PHASE 1: Content Discovery ===")
        queue_ids: list[int] = []

        # Step 1a: scrape
        try:
            scraper = ApifyScraper()
            raw_content = scraper.get_top_content(count)
        except Exception as exc:
            logger.error("Scraping failed: %s", exc)
            raw_content = []

        if not raw_content:
            logger.warning("No content discovered — skipping analysis")
            return queue_ids

        # Step 1b: analyse
        try:
            analyzer = GeminiAnalyzer()
            analyses = analyzer.analyze_content(raw_content)
        except Exception as exc:
            logger.error("Analysis failed: %s", exc)
            analyses = []

        if not analyses:
            logger.warning("No analyses produced")
            return queue_ids

        # Step 1c: queue
        for item in analyses:
            try:
                row_id = self.db.add_content(
                    source_url=item.get("source_url", ""),
                    topic=item.get("topic", ""),
                    script=json.dumps(item.get("script", item), default=str),
                    caption=item.get("caption", ""),
                )
                queue_ids.append(row_id)
            except Exception as exc:
                logger.error("Failed to queue item: %s", exc)

        logger.info("Discovery complete: %d items queued", len(queue_ids))
        return queue_ids

    # ── Phase 2+3+4: Generation ──────────────────────────────────────────

    def run_generation(self, queue_ids: list[int]) -> list[int]:
        """Generate video + audio + compose final for each queued item.

        Returns IDs of successfully generated items.
        """
        logger.info("=== PHASE 2-4: Content Generation ===")

        soul_id = Config.SOUL_ID
        if not soul_id:
            logger.warning(
                "Soul ID not configured. Run: python main.py --setup-soul-id"
            )
            return []

        video_gen = HiggsFieldGenerator()
        voice = ElevenLabsVoice()
        editor = VideoEditor()

        generated_ids: list[int] = []

        for qid in queue_ids:
            content = self.db.get_content(qid)
            if not content:
                continue

            self.db.update_content_status(qid, "generating")
            logger.info("Generating content id=%d topic=%s", qid, content.get("topic", ""))

            try:
                # Parse script
                script_raw = content.get("script", "{}")
                try:
                    script = json.loads(script_raw) if isinstance(script_raw, str) else script_raw
                except json.JSONDecodeError:
                    script = {"full_script": script_raw, "hook": script_raw[:80]}

                hook = script.get("hook", content.get("topic", "AI content"))
                caption = content.get("caption", "")

                # Phase 2: generate video
                video_path = video_gen.generate_video(hook, soul_id)
                if not video_path:
                    logger.warning("Video generation failed for id=%d", qid)
                    self.db.update_content_status(qid, "failed")
                    continue

                # Phase 3: synthesize voice
                audio_path = voice.synthesize_script(script)
                if not audio_path:
                    logger.warning("Voice synthesis failed for id=%d", qid)
                    self.db.update_content_status(qid, "failed", video_path=video_path)
                    continue

                # Phase 4: compose final video
                final_path = editor.compose_final(
                    video_path=video_path,
                    audio_path=audio_path,
                    caption=caption,
                    hook=hook,
                )
                if not final_path:
                    logger.warning("Video composition failed for id=%d", qid)
                    self.db.update_content_status(
                        qid, "failed",
                        video_path=video_path,
                        audio_path=audio_path,
                    )
                    continue

                # Success
                self.db.update_content_status(
                    qid, "generated",
                    video_path=video_path,
                    audio_path=audio_path,
                    final_video_path=final_path,
                )
                generated_ids.append(qid)
                logger.info("Content id=%d generated successfully", qid)

            except Exception as exc:
                logger.error("Generation failed for id=%d: %s", qid, exc)
                self.db.update_content_status(qid, "failed")

        logger.info("Generation complete: %d/%d succeeded", len(generated_ids), len(queue_ids))
        return generated_ids

    # ── Phase 5: Scheduling ──────────────────────────────────────────────

    def run_scheduling(
        self, queue_ids: list[int], platforms: list[str] | None = None
    ) -> list[int]:
        """Schedule all generated videos for posting.

        Returns IDs of successfully scheduled items.
        """
        logger.info("=== PHASE 5: Scheduling ===")
        platforms = platforms or Config.PLATFORMS

        blotato = BlatoScheduler()
        if not Config.BLOTATO_API_KEY:
            logger.warning("BLOTATO_API_KEY not set — skipping scheduling")
            return []

        # Build batch input from generated items
        batch: list[dict[str, str]] = []
        id_map: dict[int, int] = {}  # batch_index -> queue_id

        for qid in queue_ids:
            content = self.db.get_content(qid)
            if not content or content.get("status") != "generated":
                continue
            final_path = content.get("final_video_path", "")
            if not final_path:
                continue
            idx = len(batch)
            batch.append({
                "video_path": final_path,
                "caption": content.get("caption", ""),
            })
            id_map[idx] = qid

        if not batch:
            logger.warning("No generated videos to schedule")
            return []

        submission_ids = blotato.schedule_batch(batch, platforms)

        scheduled_ids: list[int] = []
        for i, sub_id in enumerate(submission_ids):
            qid = id_map.get(i)
            if qid and sub_id:
                self.db.update_content_status(
                    qid, "scheduled",
                    post_submission_id=sub_id,
                )
                # Log to post_log
                for platform in platforms:
                    self.db.log_post(qid, platform, sub_id, "scheduled")
                scheduled_ids.append(qid)

        logger.info("Scheduling complete: %d/%d scheduled", len(scheduled_ids), len(queue_ids))
        return scheduled_ids

    # ── Full pipeline ────────────────────────────────────────────────────

    def run_full_pipeline(self) -> dict[str, int]:
        """Run all phases in sequence and return a summary."""
        logger.info("========================================")
        logger.info("   FULL PIPELINE RUN")
        logger.info("========================================")

        # Phase 1
        queue_ids = self.run_discovery()

        # Phase 2-4
        generated_ids = self.run_generation(queue_ids) if queue_ids else []

        # Phase 5
        scheduled_ids = self.run_scheduling(generated_ids) if generated_ids else []

        summary = {
            "discovered": len(queue_ids),
            "generated": len(generated_ids),
            "scheduled": len(scheduled_ids),
        }

        logger.info("========================================")
        logger.info("   PIPELINE SUMMARY")
        logger.info("   Discovered: %d", summary["discovered"])
        logger.info("   Generated:  %d", summary["generated"])
        logger.info("   Scheduled:  %d", summary["scheduled"])
        logger.info("========================================")

        return summary

    # ── Continuous mode ──────────────────────────────────────────────────

    def run_continuous(self, interval_hours: int = 24) -> None:
        """Run the full pipeline on a recurring schedule."""
        logger.info("Starting continuous mode — running every %d hours", interval_hours)

        # Run once immediately
        self.run_full_pipeline()

        # Schedule recurring runs
        schedule_lib.every(interval_hours).hours.do(self.run_full_pipeline)

        logger.info("Scheduler active. Press Ctrl+C to stop.")
        try:
            while True:
                schedule_lib.run_pending()
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Continuous mode stopped by user")
