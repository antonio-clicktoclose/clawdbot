# AI Content Creation & Automation Pipeline

An automated system that discovers viral social media content, generates AI videos with your likeness and voice, and schedules posts across TikTok, Instagram, and YouTube. It uses Apify for scraping, Gemini for analysis, Higgsfield for video generation, ElevenLabs for voice cloning, and Blotato for cross-platform scheduling.

## Installation

```bash
# 1. Install Python 3.11+
# 2. Install ffmpeg
#    macOS:   brew install ffmpeg
#    Linux:   sudo apt install ffmpeg
#    Windows: choco install ffmpeg

# 3. Install Python dependencies
cd ai-content-pipeline
pip install -r requirements.txt

# 4. Edit .env with your API keys (pre-filled template provided)
```

## First-Time Setup

### 1. Create your Soul ID (AI avatar)

Place 10-20 photos of yourself in `soul_id/photos/` (different angles, good lighting, JPG/PNG), then run:

```bash
python main.py --setup-soul-id
```

### 2. Clone your voice

Place 3-5 audio samples in `soul_id/voice_samples/` (30s-3min each, clear speech, MP3/WAV), then run:

```bash
python main.py --setup-voice
```

## Usage

```bash
# Run the full pipeline once
python main.py

# Run on a daily schedule
python main.py --continuous

# Run a specific phase
python main.py --phase discovery
python main.py --phase generation
python main.py --phase scheduling

# Check pipeline status
python main.py --status
```

## Dashboard

A built-in web dashboard lets you monitor the entire pipeline in real time:

```bash
# Start the dashboard (default: http://localhost:5050)
python dashboard.py

# Custom port
python dashboard.py --port 8080
```

The dashboard shows:
- **Summary cards** — total items, status breakdown, configuration health
- **Content Queue** — every item with status, topic, caption, source link
- **Post Log** — scheduled posts per platform with timestamps
- **API Keys** — which keys are configured (values are never exposed)
- **Output Files** — generated videos, audio, and final composed files
- **Pipeline Logs** — color-coded live log viewer (auto-refreshes every 30s)

## Troubleshooting

- **"Soul ID not configured"** — Run `python main.py --setup-soul-id` first.
- **"ffmpeg not found"** — Install ffmpeg at the system level (see Installation).
- **API errors** — Check that all keys in `.env` are valid and have sufficient credits.
- **Rate limits** — The pipeline spaces API calls automatically; wait and re-run if throttled.
- **Empty results** — Apify actors may be temporarily unavailable; check the Apify dashboard.
