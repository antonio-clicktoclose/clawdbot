"""
Phase 3: ElevenLabs voice cloning and text-to-speech synthesis.
"""

import logging
from pathlib import Path
from typing import Any

from elevenlabs.client import ElevenLabs

from config import Config
from utils.file_manager import FileManager

logger = logging.getLogger("pipeline.voice")


class ElevenLabsVoice:
    """Clones voices and synthesizes speech via the ElevenLabs API."""

    def __init__(self) -> None:
        self.api_key = Config.ELEVENLABS_API_KEY
        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY not set — voice synthesis will be skipped")
            self.client = None
        else:
            self.client = ElevenLabs(api_key=self.api_key)

    # ── Voice cloning ────────────────────────────────────────────────────

    def clone_voice(
        self,
        audio_sample_paths: list[Path],
        voice_name: str = "Antonio",
    ) -> str | None:
        """Clone a voice from audio samples.

        Returns the voice_id on success.
        """
        if not self.client:
            logger.error("Cannot clone voice: ElevenLabs client not initialized")
            return None

        if not audio_sample_paths:
            logger.error("No audio samples provided for voice cloning")
            return None

        try:
            files = []
            for p in audio_sample_paths:
                files.append(open(p, "rb"))

            voice = self.client.clone(
                name=voice_name,
                files=files,
                description=f"Cloned voice: {voice_name}",
            )

            for f in files:
                f.close()

            voice_id = voice.voice_id
            Config.update_env("ELEVENLABS_VOICE_ID", voice_id)
            logger.info("Voice cloned successfully: %s (id=%s)", voice_name, voice_id)
            return voice_id

        except Exception as exc:
            logger.error("Voice cloning failed: %s", exc)
            return None

    # ── Voice selection ──────────────────────────────────────────────────

    def _resolve_voice_id(self, voice_id: str | None = None) -> str | None:
        """Resolve the voice ID to use: explicit > config > first available."""
        if voice_id:
            return voice_id
        if Config.ELEVENLABS_VOICE_ID:
            return Config.ELEVENLABS_VOICE_ID

        # Fall back to first available voice
        if not self.client:
            return None
        try:
            voices = self.client.voices.get_all()
            voice_list = voices.voices if hasattr(voices, "voices") else voices
            if voice_list:
                fallback_id = voice_list[0].voice_id
                logger.info("Using fallback voice: %s", fallback_id)
                return fallback_id
        except Exception as exc:
            logger.error("Failed to list voices: %s", exc)
        return None

    # ── Text-to-speech ───────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        output_path: str | None = None,
    ) -> str | None:
        """Convert text to speech and save as MP3.

        Returns the output file path on success.
        """
        if not self.client:
            logger.error("Cannot synthesize: ElevenLabs client not initialized")
            return None

        resolved_id = self._resolve_voice_id(voice_id)
        if not resolved_id:
            logger.error("No voice ID available for synthesis")
            return None

        if not output_path:
            filename = FileManager.timestamped_name("voice", "mp3")
            output_path = str(Config.AUDIO_DIR / filename)

        try:
            audio_generator = self.client.text_to_speech.convert(
                voice_id=resolved_id,
                text=text,
                voice_settings={
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                    "style": 0.3,
                    "use_speaker_boost": True,
                },
            )

            # Write audio bytes to file
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)

            if FileManager.verify_file(out):
                logger.info("Synthesized audio saved: %s", out)
                return str(out)
            return None

        except Exception as exc:
            logger.error("Speech synthesis failed: %s", exc)
            return None

    def synthesize_script(
        self,
        script_dict: dict[str, Any],
        voice_id: str | None = None,
    ) -> str | None:
        """Synthesize the full_script field from a Gemini script dict.

        Returns the audio file path on success.
        """
        full_script = script_dict.get("full_script", "")
        if not full_script:
            # Fall back to concatenating hook + body + cta
            parts = [
                script_dict.get("hook", ""),
                script_dict.get("body", ""),
                script_dict.get("cta", ""),
            ]
            full_script = " ".join(p for p in parts if p)

        if not full_script:
            logger.error("No script text to synthesize")
            return None

        return self.synthesize(full_script, voice_id)
