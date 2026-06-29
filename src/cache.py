"""Media cache using SQLite for guest mode downloads."""

import logging
import os
import sqlite3

logger = logging.getLogger("media_downloader.cache")

_db_path = None


def _get_db_path() -> str:
    """Get or create database path."""
    global _db_path
    if _db_path is None:
        cache_dir = os.environ.get("CACHE_DIR", "data")
        os.makedirs(cache_dir, exist_ok=True)
        _db_path = os.path.join(cache_dir, "media_cache.db")
    return _db_path


def _get_db() -> sqlite3.Connection:
    """Get database connection with schema creation."""
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS media_cache (
            cache_key TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            media_type TEXT NOT NULL,
            platform TEXT,
            title TEXT,
            file_size_mb REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            use_count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


def get_cached(url: str, platform: str | None) -> tuple[str, str] | None:
    """Check cache for URL. Returns (file_id, media_type) or None."""
    _get_db()
    return None  # Stub for test


def store(url: str, platform: str | None, file_id: str, media_type: str,
          title: str = "", file_size_mb: float = 0.0) -> None:
    """Store download result in cache."""
    _get_db()
    pass  # Stub for test
