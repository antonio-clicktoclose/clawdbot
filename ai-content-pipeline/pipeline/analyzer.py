"""
Phase 1b: Gemini-powered content analysis and script generation.
"""

import json
import logging
import time
from typing import Any

import google.generativeai as genai

from config import Config

logger = logging.getLogger("pipeline.analyzer")

ANALYSIS_PROMPT = """Analyze this viral social media content and extract:
1. Main hook (first 3 seconds concept)
2. Core topic/theme
3. Target audience
4. Emotional trigger used (curiosity, fear, desire, etc.)
5. Content structure (problem-solution, list, story, etc.)
6. Suggested script for a 60-second video on this topic
7. Suggested caption with 5 hashtags

Content: {description}
Platform: {platform}
Engagement metrics: {likes} likes, {views} views, {shares} shares

Respond in JSON format with keys: hook, topic, audience, emotion, structure, script, caption"""

SCRIPT_PROMPT = """Write a {style} 60-second video script on the topic: {topic}

The script must include:
1. A punchy hook for the first 3 seconds
2. A body that delivers value in 45 seconds
3. A clear call-to-action for the last 12 seconds

Respond in JSON format with keys: hook, body, cta, full_script, caption
The full_script should be the complete text read aloud, combining hook + body + cta."""


class GeminiAnalyzer:
    """Uses Google Gemini to analyze scraped content and generate scripts."""

    def __init__(self) -> None:
        if not Config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY is not set in .env")
        genai.configure(api_key=Config.GEMINI_API_KEY)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    def _call_gemini(self, prompt: str) -> dict[str, Any]:
        """Send a prompt to Gemini and parse the JSON response."""
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()

            # Strip markdown code fences if present
            if text.startswith("```"):
                lines = text.split("\n")
                # Remove first and last lines (```json and ```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                text = "\n".join(lines)

            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini response was not valid JSON, wrapping as raw text")
            return {"raw_response": text}
        except Exception as exc:
            logger.error("Gemini API call failed: %s", exc)
            return {}

    def analyze_content(self, content_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Analyze a list of scraped content items with Gemini.

        Returns a list of analysis dicts (one per input item).
        """
        results: list[dict[str, Any]] = []
        for i, item in enumerate(content_list):
            logger.info("Analyzing item %d/%d: %s", i + 1, len(content_list), item.get("url", ""))
            prompt = ANALYSIS_PROMPT.format(
                description=item.get("description", ""),
                platform=item.get("platform", "unknown"),
                likes=item.get("likes", 0),
                views=item.get("views", 0),
                shares=item.get("shares", 0),
            )
            analysis = self._call_gemini(prompt)
            if analysis:
                analysis["source_url"] = item.get("url", "")
                analysis["platform"] = item.get("platform", "unknown")
                results.append(analysis)

            # Rate-limit guard: 2-second delay between calls
            if i < len(content_list) - 1:
                time.sleep(2)

        logger.info("Analyzed %d/%d items successfully", len(results), len(content_list))
        return results

    def generate_script(
        self, topic: str, style: str = "educational"
    ) -> dict[str, Any]:
        """Generate a standalone 60-second video script on a given topic.

        Styles: educational, motivational, story, tips.
        """
        valid_styles = {"educational", "motivational", "story", "tips"}
        if style not in valid_styles:
            logger.warning("Unknown style '%s', defaulting to 'educational'", style)
            style = "educational"

        prompt = SCRIPT_PROMPT.format(topic=topic, style=style)
        result = self._call_gemini(prompt)
        if result:
            logger.info("Generated %s script for topic: %s", style, topic)
        return result
