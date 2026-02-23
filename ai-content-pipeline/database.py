"""
SQLite state tracking for the content pipeline.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import Config

logger = logging.getLogger("pipeline.db")


class Database:
    """CRUD wrapper around the pipeline SQLite database."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    # ── Connection helpers ───────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Schema ───────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS content_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_url TEXT,
                topic TEXT,
                script TEXT,
                caption TEXT,
                status TEXT DEFAULT 'pending',
                video_path TEXT,
                audio_path TEXT,
                final_video_path TEXT,
                post_submission_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS soul_id_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                soul_id TEXT,
                voice_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS post_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id INTEGER,
                platform TEXT,
                post_id TEXT,
                status TEXT,
                posted_at DATETIME,
                FOREIGN KEY (content_id) REFERENCES content_queue(id)
            );
            """
        )
        conn.commit()
        logger.debug("Database initialized at %s", self.db_path)

    # ── content_queue CRUD ───────────────────────────────────────────────

    def add_content(
        self,
        source_url: str,
        topic: str,
        script: str,
        caption: str,
    ) -> int:
        """Insert a new content item. Returns the row id."""
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO content_queue (source_url, topic, script, caption, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (source_url, topic, script, caption),
        )
        conn.commit()
        row_id = cur.lastrowid or 0
        logger.debug("Added content id=%d topic=%s", row_id, topic)
        return row_id

    def update_content_status(self, content_id: int, status: str, **fields: Any) -> None:
        """Update status and optional extra fields for a content item."""
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        set_clauses = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now]
        for key, val in fields.items():
            set_clauses.append(f"{key} = ?")
            params.append(val)
        params.append(content_id)
        conn.execute(
            f"UPDATE content_queue SET {', '.join(set_clauses)} WHERE id = ?",
            params,
        )
        conn.commit()
        logger.debug("Updated content id=%d status=%s", content_id, status)

    def get_content(self, content_id: int) -> dict[str, Any] | None:
        """Fetch a single content item by id."""
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM content_queue WHERE id = ?", (content_id,)).fetchone()
        return dict(row) if row else None

    def get_contents_by_status(self, status: str) -> list[dict[str, Any]]:
        """Fetch all content items with the given status."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM content_queue WHERE status = ? ORDER BY created_at",
            (status,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_contents(self) -> list[dict[str, Any]]:
        """Fetch all content items."""
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM content_queue ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    # ── soul_id_registry CRUD ────────────────────────────────────────────

    def save_soul_id(self, soul_id: str, voice_id: str = "") -> int:
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO soul_id_registry (soul_id, voice_id) VALUES (?, ?)",
            (soul_id, voice_id),
        )
        conn.commit()
        return cur.lastrowid or 0

    def get_latest_soul_id(self) -> dict[str, Any] | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM soul_id_registry ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    # ── post_log CRUD ────────────────────────────────────────────────────

    def log_post(
        self, content_id: int, platform: str, post_id: str, status: str
    ) -> int:
        conn = self._get_conn()
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO post_log (content_id, platform, post_id, status, posted_at)
               VALUES (?, ?, ?, ?, ?)""",
            (content_id, platform, post_id, status, now),
        )
        conn.commit()
        return cur.lastrowid or 0

    def get_post_logs(self, content_id: int | None = None) -> list[dict[str, Any]]:
        conn = self._get_conn()
        if content_id:
            rows = conn.execute(
                "SELECT * FROM post_log WHERE content_id = ? ORDER BY posted_at DESC",
                (content_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM post_log ORDER BY posted_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Summary ──────────────────────────────────────────────────────────

    def pipeline_summary(self) -> dict[str, int]:
        """Return counts by status for the content_queue."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM content_queue GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}
