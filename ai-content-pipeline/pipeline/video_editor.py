"""
Phase 4: FFmpeg-based video composition — audio overlay, captions, intros.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from config import Config
from utils.file_manager import FileManager

logger = logging.getLogger("pipeline.video_editor")


def _check_ffmpeg() -> bool:
    """Verify that ffmpeg is available on the system."""
    if shutil.which("ffmpeg") is None:
        logger.error(
            "ffmpeg not found. Install it:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Linux:  sudo apt install ffmpeg\n"
            "  Windows: choco install ffmpeg"
        )
        return False
    return True


class VideoEditor:
    """Composes final videos using ffmpeg-python (and raw ffmpeg fallback)."""

    def __init__(self) -> None:
        self.ffmpeg_ok = _check_ffmpeg()

    def _run_ffmpeg(self, args: list[str]) -> bool:
        """Execute an ffmpeg command. Returns True on success."""
        if not self.ffmpeg_ok:
            logger.error("ffmpeg is not installed — cannot process video")
            return False

        cmd = ["ffmpeg", "-y"] + args  # -y to overwrite
        logger.debug("Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.error("ffmpeg error: %s", result.stderr[-500:] if result.stderr else "unknown")
                return False
            return True
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg timed out after 300s")
            return False
        except Exception as exc:
            logger.error("ffmpeg execution failed: %s", exc)
            return False

    # ── Audio overlay ────────────────────────────────────────────────────

    def add_audio_to_video(
        self, video_path: str, audio_path: str, output_path: str
    ) -> str | None:
        """Merge AI video with voiceover audio.

        - If audio is longer, loop the video.
        - If video is longer, trim to audio length.
        - Output: 1080x1920 (9:16 vertical).
        """
        # Get durations
        v_dur = self._get_duration(video_path)
        a_dur = self._get_duration(audio_path)

        if v_dur <= 0 or a_dur <= 0:
            logger.error("Could not determine media durations (video=%.1f, audio=%.1f)", v_dur, a_dur)
            return None

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if a_dur > v_dur:
            # Loop video to match audio length
            args = [
                "-stream_loop", "-1", "-i", video_path,
                "-i", audio_path,
                "-t", str(a_dur),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-shortest",
                output_path,
            ]
        else:
            # Trim video to audio length
            args = [
                "-i", video_path,
                "-i", audio_path,
                "-t", str(a_dur),
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                output_path,
            ]

        if self._run_ffmpeg(args) and FileManager.verify_file(Path(output_path)):
            logger.info("Audio merged: %s", output_path)
            return output_path
        return None

    # ── Captions ─────────────────────────────────────────────────────────

    def add_captions(
        self, video_path: str, caption_text: str, output_path: str
    ) -> str | None:
        """Burn captions onto video using drawtext filter.

        White bold text with black outline, positioned at bottom 20%.
        """
        # Wrap text at 40 chars
        lines = []
        words = caption_text.split()
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 > 40:
                lines.append(current_line)
                current_line = word
            else:
                current_line = f"{current_line} {word}".strip()
        if current_line:
            lines.append(current_line)
        wrapped = "\\n".join(lines)

        # Escape special chars for ffmpeg drawtext
        safe_text = wrapped.replace("'", "\u2019").replace(":", "\\:")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        args = [
            "-i", video_path,
            "-vf", (
                f"drawtext=text='{safe_text}'"
                f":fontsize=36:fontcolor=white"
                f":borderw=2:bordercolor=black"
                f":x=(w-text_w)/2:y=h*0.80"
            ),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "copy",
            output_path,
        ]

        if self._run_ffmpeg(args) and FileManager.verify_file(Path(output_path)):
            logger.info("Captions added: %s", output_path)
            return output_path
        return None

    # ── Intro card ───────────────────────────────────────────────────────

    def add_intro_card(
        self, video_path: str, hook_text: str, output_path: str
    ) -> str | None:
        """Add a 2-second text card at the beginning with a fade transition."""
        safe_text = hook_text.replace("'", "\u2019").replace(":", "\\:")

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Create a 2s black card with text, then concatenate with main video
        # Using complex filter: generate black bg + text, fade, concat
        filter_complex = (
            # Generate 2-second black background at 1080x1920
            f"color=c=black:s=1080x1920:d=2:r=24[bg];"
            # Draw hook text on the black background
            f"[bg]drawtext=text='{safe_text}'"
            f":fontsize=48:fontcolor=white"
            f":x=(w-text_w)/2:y=(h-text_h)/2"
            f",fade=t=in:st=0:d=0.5"
            f",fade=t=out:st=1.5:d=0.5[intro];"
            # Scale the main video
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2[main];"
            # Concatenate intro + main
            f"[intro][main]concat=n=2:v=1:a=0[outv]"
        )

        args = [
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-an",  # We'll add audio separately
            output_path,
        ]

        if self._run_ffmpeg(args) and FileManager.verify_file(Path(output_path)):
            logger.info("Intro card added: %s", output_path)
            return output_path
        return None

    # ── Full composition ─────────────────────────────────────────────────

    def compose_final(
        self,
        video_path: str,
        audio_path: str,
        caption: str,
        hook: str,
        output_path: str | None = None,
    ) -> str | None:
        """Run the full composition pipeline:
        1. Add intro card
        2. Merge with audio
        3. Burn captions
        """
        if not output_path:
            filename = FileManager.timestamped_name("final", "mp4")
            output_path = str(Config.FINAL_DIR / filename)

        temp_dir = Config.OUTPUTS_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: intro card
            intro_path = str(temp_dir / "step1_intro.mp4")
            result = self.add_intro_card(video_path, hook, intro_path)
            if not result:
                logger.warning("Intro card failed, continuing without it")
                intro_path = video_path

            # Step 2: merge audio
            merged_path = str(temp_dir / "step2_merged.mp4")
            result = self.add_audio_to_video(intro_path, audio_path, merged_path)
            if not result:
                logger.warning("Audio merge failed, continuing with video only")
                merged_path = intro_path

            # Step 3: burn captions
            result = self.add_captions(merged_path, caption, output_path)
            if not result:
                logger.warning("Caption burn failed, using merged video as final")
                # Copy the best result so far
                import shutil as _shutil
                _shutil.copy2(merged_path, output_path)

            if FileManager.verify_file(Path(output_path)):
                logger.info("Final video composed: %s", output_path)
                return output_path
            return None

        except Exception as exc:
            logger.error("Video composition failed: %s", exc)
            return None
        finally:
            # Clean temp files
            for f in temp_dir.iterdir():
                if f.is_file():
                    f.unlink()

    # ── Thumbnail ────────────────────────────────────────────────────────

    def create_thumbnail(self, video_path: str, output_path: str | None = None) -> str | None:
        """Extract a frame at 2 seconds as a JPEG thumbnail."""
        if not output_path:
            filename = FileManager.timestamped_name("thumb", "jpg")
            output_path = str(Config.FINAL_DIR / filename)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        args = [
            "-i", video_path,
            "-ss", "2",
            "-vframes", "1",
            "-q:v", "2",
            output_path,
        ]

        if self._run_ffmpeg(args) and FileManager.verify_file(Path(output_path)):
            logger.info("Thumbnail created: %s", output_path)
            return output_path
        return None

    # ── Helpers ──────────────────────────────────────────────────────────

    def _get_duration(self, file_path: str) -> float:
        """Get media duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    file_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return float(result.stdout.strip())
        except Exception as exc:
            logger.error("ffprobe failed for %s: %s", file_path, exc)
            return 0.0
