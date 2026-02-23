#!/usr/bin/env python3
"""
AI Content Creation & Automation Pipeline

Usage:
  python main.py                    # Run full pipeline once
  python main.py --continuous       # Run daily on schedule
  python main.py --phase discovery  # Run only discovery
  python main.py --phase generation # Run only generation
  python main.py --phase scheduling # Run only scheduling
  python main.py --setup-soul-id    # Walk through Soul ID creation
  python main.py --setup-voice      # Walk through voice clone creation
  python main.py --status           # Show pipeline status from DB
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from database import Database
from utils.logger import setup_logger
from utils.file_manager import FileManager

logger = setup_logger()


def show_status() -> None:
    """Display current pipeline status from the database."""
    Config.ensure_dirs()
    db = Database()
    summary = db.pipeline_summary()
    all_items = db.get_all_contents()

    print("\n=== Pipeline Status ===")
    if not summary:
        print("  No content in the pipeline yet.")
        print("  Run 'python main.py' to start content discovery.")
    else:
        print(f"  Total items: {sum(summary.values())}")
        for status, count in sorted(summary.items()):
            print(f"    {status}: {count}")

    # Show recent items
    if all_items:
        print(f"\n  Recent items (last 10):")
        for item in all_items[:10]:
            print(
                f"    [{item['id']}] {item['status']:12s} | "
                f"{(item.get('topic') or 'no topic')[:50]} | "
                f"{item['created_at']}"
            )

    # Show Soul ID / Voice config
    print("\n=== Configuration ===")
    print(f"  Soul ID:        {'configured' if Config.SOUL_ID else 'NOT SET — run --setup-soul-id'}")
    print(f"  Voice ID:       {'configured' if Config.ELEVENLABS_VOICE_ID else 'NOT SET — run --setup-voice'}")
    print(f"  Posts per day:   {Config.POSTS_PER_DAY}")
    print(f"  Platforms:       {', '.join(Config.PLATFORMS)}")
    print(f"  Approval mode:   {Config.APPROVAL_MODE}")
    print()

    db.close()


def setup_soul_id() -> None:
    """Interactive Soul ID creation walkthrough."""
    Config.ensure_dirs()

    print("\n" + "=" * 50)
    print("  SOUL ID SETUP")
    print("=" * 50)
    print(f"""
Place 10-20 photos of yourself in: {Config.PHOTOS_DIR}/

Requirements:
  - Different angles (front, left, right, slight up/down)
  - Good lighting, face clearly visible
  - Neutral and expressive facial expressions
  - No filters or heavy edits
  - JPG or PNG format
""")

    input("Press ENTER when photos are ready...")

    photos = FileManager.list_files(Config.PHOTOS_DIR, extensions=(".jpg", ".jpeg", ".png"))
    if len(photos) < 5:
        print(f"\nError: Found {len(photos)} photos — need at least 5.")
        print(f"Add more photos to: {Config.PHOTOS_DIR}/")
        sys.exit(1)

    print(f"\nFound {len(photos)} photos. Creating Soul ID...")

    from pipeline.video_generator import HiggsFieldGenerator

    generator = HiggsFieldGenerator()
    soul_id = generator.create_soul_id(photos)

    if soul_id:
        print(f"\nSoul ID created and saved: {soul_id}")
        print("You can now run the full pipeline: python main.py")
    else:
        print("\nSoul ID creation failed. Check the logs for details.")
        sys.exit(1)


def setup_voice() -> None:
    """Interactive voice clone creation walkthrough."""
    Config.ensure_dirs()
    samples_dir = Config.VOICE_SAMPLES_DIR

    print("\n" + "=" * 50)
    print("  VOICE CLONE SETUP")
    print("=" * 50)
    print(f"""
Place 3-5 audio samples of your voice in: {samples_dir}/

Requirements:
  - 30 seconds to 3 minutes each
  - Clear speech, no background noise
  - MP3 or WAV format
  - Speak naturally as if recording a podcast
""")

    input("Press ENTER when samples are ready...")

    samples = FileManager.list_files(samples_dir, extensions=(".mp3", ".wav", ".m4a"))
    if not samples:
        print(f"\nError: No audio samples found in {samples_dir}/")
        print("Add MP3 or WAV files and try again.")
        sys.exit(1)

    print(f"\nFound {len(samples)} audio samples. Cloning voice...")

    from pipeline.voice_synthesizer import ElevenLabsVoice

    voice = ElevenLabsVoice()
    voice_id = voice.clone_voice(samples)

    if voice_id:
        print(f"\nVoice clone created and saved: {voice_id}")
        print("You can now run the full pipeline: python main.py")
    else:
        print("\nVoice cloning failed. Check the logs for details.")
        sys.exit(1)


def run_pipeline(phase: str | None = None, continuous: bool = False) -> None:
    """Run the content pipeline (full or a specific phase)."""
    Config.ensure_dirs()

    from pipeline.orchestrator import PipelineOrchestrator

    orchestrator = PipelineOrchestrator()

    if continuous:
        orchestrator.run_continuous()
        return

    if phase == "discovery":
        ids = orchestrator.run_discovery()
        print(f"\nDiscovery complete: {len(ids)} items queued")
    elif phase == "generation":
        # Generate all pending items
        db = Database()
        pending = db.get_contents_by_status("pending")
        ids = [item["id"] for item in pending]
        if not ids:
            print("No pending items to generate. Run discovery first.")
            return
        generated = orchestrator.run_generation(ids)
        print(f"\nGeneration complete: {len(generated)}/{len(ids)} succeeded")
        db.close()
    elif phase == "scheduling":
        # Schedule all generated items
        db = Database()
        generated = db.get_contents_by_status("generated")
        ids = [item["id"] for item in generated]
        if not ids:
            print("No generated items to schedule. Run generation first.")
            return
        scheduled = orchestrator.run_scheduling(ids)
        print(f"\nScheduling complete: {len(scheduled)}/{len(ids)} scheduled")
        db.close()
    else:
        # Full pipeline
        summary = orchestrator.run_full_pipeline()
        print(f"\nPipeline complete:")
        print(f"  Discovered: {summary['discovered']}")
        print(f"  Generated:  {summary['generated']}")
        print(f"  Scheduled:  {summary['scheduled']}")


def main() -> None:
    """Entry point — parse CLI arguments and dispatch."""
    parser = argparse.ArgumentParser(
        description="AI Content Creation & Automation Pipeline"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run the pipeline on a recurring schedule",
    )
    parser.add_argument(
        "--phase",
        choices=["discovery", "generation", "scheduling"],
        help="Run only a specific pipeline phase",
    )
    parser.add_argument(
        "--setup-soul-id",
        action="store_true",
        help="Interactive Soul ID creation",
    )
    parser.add_argument(
        "--setup-voice",
        action="store_true",
        help="Interactive voice clone creation",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show pipeline status from DB",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.setup_soul_id:
        setup_soul_id()
    elif args.setup_voice:
        setup_voice()
    else:
        run_pipeline(phase=args.phase, continuous=args.continuous)


if __name__ == "__main__":
    main()
