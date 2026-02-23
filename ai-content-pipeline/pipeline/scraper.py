"""
Phase 1a: Apify-based content scraping from TikTok, Instagram, and YouTube.
"""

import json
import logging
import random
import time
from typing import Any

from apify_client import ApifyClient

from config import Config
from utils.file_manager import FileManager

logger = logging.getLogger("pipeline.scraper")

TIKTOK_SEARCH_TERMS = [
    "make money online",
    "sales tips",
    "business automation",
    "AI tools",
    "entrepreneur mindset",
]

INSTAGRAM_HASHTAGS = [
    "businesstips",
    "salesautomation",
    "entrepreneurship",
    "aitools",
    "makemoney",
]


class ApifyScraper:
    """Scrapes viral content from TikTok, Instagram, and YouTube via Apify."""

    def __init__(self) -> None:
        if not Config.APIFY_API_TOKEN:
            raise ValueError("APIFY_API_TOKEN is not set in .env")
        self.client = ApifyClient(Config.APIFY_API_TOKEN)

    # ── Private helpers ──────────────────────────────────────────────────

    def _run_actor(
        self, actor_id: str, run_input: dict[str, Any], timeout: int = 60
    ) -> list[dict[str, Any]]:
        """Start an Apify actor run, poll until complete, and return items."""
        logger.info("Starting Apify actor %s", actor_id)
        run = self.client.actor(actor_id).call(run_input=run_input, timeout_secs=timeout)
        if not run:
            logger.error("Actor %s returned no run object", actor_id)
            return []
        items: list[dict[str, Any]] = []
        for item in self.client.dataset(run["defaultDatasetId"]).iterate_items():
            items.append(item)
        logger.info("Actor %s returned %d items", actor_id, len(items))
        return items

    @staticmethod
    def _engagement_score(item: dict[str, Any]) -> float:
        likes = item.get("likes", 0) or 0
        shares = item.get("shares", 0) or 0
        views = item.get("views", 1) or 1
        return (likes + shares) / max(views, 1)

    # ── Public scrapers ──────────────────────────────────────────────────

    def scrape_viral_tiktok(self, count: int = 10) -> list[dict[str, Any]]:
        """Scrape viral TikTok videos using the free TikTok scraper."""
        search_term = random.choice(TIKTOK_SEARCH_TERMS)
        run_input = {
            "resultsPerPage": count,
            "searchSection": "videos",
            "maxProfilesPerQuery": 5,
            "searchQueries": [search_term],
        }
        try:
            raw = self._run_actor("clockworks/free-tiktok-scraper", run_input)
        except Exception as exc:
            logger.error("TikTok scrape failed: %s", exc)
            return []

        results = []
        for item in raw:
            results.append(
                {
                    "url": item.get("webVideoUrl", item.get("url", "")),
                    "description": item.get("text", item.get("desc", "")),
                    "likes": item.get("diggCount", item.get("likes", 0)),
                    "shares": item.get("shareCount", item.get("shares", 0)),
                    "views": item.get("playCount", item.get("views", 0)),
                    "author": item.get("authorMeta", {}).get("name", item.get("author", "")),
                    "platform": "tiktok",
                }
            )
        FileManager.save_json(results, Config.LOGS_DIR, "scrape_tiktok")
        return results

    def scrape_viral_instagram(self, count: int = 10) -> list[dict[str, Any]]:
        """Scrape viral Instagram posts by hashtag."""
        hashtag = random.choice(INSTAGRAM_HASHTAGS)
        run_input = {
            "hashtags": [hashtag],
            "resultsLimit": count,
        }
        try:
            raw = self._run_actor("apify/instagram-hashtag-scraper", run_input)
        except Exception as exc:
            logger.error("Instagram scrape failed: %s", exc)
            return []

        results = []
        for item in raw:
            results.append(
                {
                    "url": item.get("url", ""),
                    "description": item.get("caption", item.get("text", "")),
                    "likes": item.get("likesCount", item.get("likes", 0)),
                    "shares": item.get("sharesCount", item.get("shares", 0)),
                    "views": item.get("videoViewCount", item.get("views", 0)),
                    "author": item.get("ownerUsername", item.get("author", "")),
                    "platform": "instagram",
                }
            )
        FileManager.save_json(results, Config.LOGS_DIR, "scrape_instagram")
        return results

    def scrape_viral_youtube(self, count: int = 5) -> list[dict[str, Any]]:
        """Scrape viral YouTube videos."""
        search_term = random.choice(TIKTOK_SEARCH_TERMS)
        run_input = {
            "searchKeywords": search_term,
            "maxResults": count,
        }
        try:
            raw = self._run_actor("streamers/youtube-scraper", run_input)
        except Exception as exc:
            logger.error("YouTube scrape failed: %s", exc)
            return []

        results = []
        for item in raw:
            results.append(
                {
                    "url": item.get("url", ""),
                    "description": item.get("title", item.get("description", "")),
                    "likes": item.get("likes", 0),
                    "shares": item.get("shares", 0),
                    "views": item.get("viewCount", item.get("views", 0)),
                    "author": item.get("channelName", item.get("author", "")),
                    "platform": "youtube",
                }
            )
        FileManager.save_json(results, Config.LOGS_DIR, "scrape_youtube")
        return results

    def get_top_content(self, count: int = 20) -> list[dict[str, Any]]:
        """Combine results from all platforms and return the top items by engagement."""
        logger.info("Starting content discovery across all platforms")

        all_content: list[dict[str, Any]] = []
        all_content.extend(self.scrape_viral_tiktok())
        all_content.extend(self.scrape_viral_instagram())
        all_content.extend(self.scrape_viral_youtube())

        if not all_content:
            logger.warning("No content scraped from any platform")
            return []

        all_content.sort(key=self._engagement_score, reverse=True)
        top = all_content[:count]

        FileManager.save_json(top, Config.LOGS_DIR, "scrape_top")
        logger.info("Returning top %d items from %d total", len(top), len(all_content))
        return top
