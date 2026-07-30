"""Media cache using SQLite for guest mode downloads."""

import hashlib
import logging
import os
import re
import sqlite3

import httpx

from logging_config import get_current_request_id

logger = logging.getLogger("media_downloader.cache")
details_logger = logging.getLogger("media_downloader.details")

_db_path = None
_conn = None

# In-memory cache for TikTok redirect resolution (short URL -> video ID)
_redirect_cache: dict[str, str | None] = {}


def _log_extra(url: str, cache_key: str) -> dict:
    """Build extra fields for structured detail logging."""
    extra = {"url": url, "cache_key": cache_key}
    request_id = get_current_request_id()
    if request_id:
        extra["request_id"] = request_id
    return extra


def _extract_tiktok_id(url: str) -> str | None:
    """Extract video ID from TikTok URL.

    Returns ID for full URLs (tiktok.com/@user/video/ID), None for short URLs (vt.tiktok.com).
    """
    match = re.search(r'tiktok\.com/@[^/]+/video/(\d+)', url)
    if match:
        return match.group(1)
    return None


def _extract_youtube_id(url: str) -> str | None:
    """Extract video ID from YouTube URL.

    Supports: youtube.com/watch?v=ID, youtu.be/ID
    """
    match = re.search(r'[?&]v=([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', url)
    if match:
        return match.group(1)
    return None


def _extract_instagram_shortcode(url: str) -> str | None:
    """Extract shortcode from Instagram URL.

    Supports: instagram.com/p/SHORTCODE, instagram.com/reel/SHORTCODE
    """
    match = re.search(r'instagram\.com/(?:p|reel)/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return None


def _resolve_tiktok_redirect(url: str) -> str | None:
    """Resolve a TikTok short URL to its video ID via HTTP redirect.

    Uses httpx to follow redirects and extract the video ID from the final URL.
    Results are cached in-memory to avoid repeated HTTP requests.

    Returns video ID or None if resolution fails.
    """
    if url in _redirect_cache:
        return _redirect_cache[url]

    try:
        with httpx.Client(timeout=5.0, follow_redirects=True) as client:
            response = client.head(url)
            final_url = str(response.url)
            video_id = _extract_tiktok_id(final_url)
            _redirect_cache[url] = video_id
            if video_id:
                details_logger.info("TikTok redirect resolved: %s -> %s", url, video_id)
            return video_id
    except Exception as e:
        logger.debug("TikTok redirect resolution failed for %s: %s", url, e)
        _redirect_cache[url] = None
        return None


def _url_hash(url: str) -> str:
    """Generate a hash-based cache key from URL.

    Used as fallback when no stable video ID can be extracted.
    """
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _metadata_hash(metadata: dict) -> str:
    """Hash title + duration + uploader for fallback key."""
    title = metadata.get("title", "")
    duration = metadata.get("duration", 0)
    uploader = metadata.get("uploader", "")
    content = f"{title}:{duration}:{uploader}"
    return hashlib.md5(content.encode()).hexdigest()[:8]


def _get_cache_key(url: str, platform: str | None, metadata: dict | None = None) -> str | None:
    """Generate cache key from URL and optional metadata.

    Returns key in format "platform:id" or None if cannot generate.
    """
    # TikTok
    if platform == "tiktok":
        video_id = _extract_tiktok_id(url)
        if video_id:
            return f"tiktok:{video_id}"
        # Try metadata for short URLs (if yt-dlp succeeded)
        if metadata and metadata.get("id"):
            return f"tiktok:{metadata['id']}"
        # Try redirect resolution for short URLs
        video_id = _resolve_tiktok_redirect(url)
        if video_id:
            return f"tiktok:{video_id}"
        # Fallback: URL hash (different short URLs get different entries)
        return f"tiktok:{_url_hash(url)}"

    # YouTube
    if platform == "youtube":
        video_id = _extract_youtube_id(url)
        if video_id:
            return f"youtube:{video_id}"
        return None

    # Instagram
    if platform == "instagram":
        shortcode = _extract_instagram_shortcode(url)
        if shortcode:
            return f"instagram:{shortcode}"
        return None

    # Unknown platform: use metadata hash
    if metadata:
        return f"meta:{_metadata_hash(metadata)}"

    return None


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
    global _conn
    if _conn is None:
        db_path = _get_db_path()
        _conn = sqlite3.connect(db_path, check_same_thread=False)
        _conn.execute("""
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
        _conn.commit()
    return _conn


def get_cached(url: str, platform: str | None, metadata: dict | None = None) -> tuple[str, str] | None:
    """Check cache for URL. Returns (file_id, media_type) or None."""
    cache_key = _get_cache_key(url, platform, metadata)
    if not cache_key:
        return None

    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT file_id, media_type FROM media_cache WHERE cache_key = ?",
            (cache_key,)
        ).fetchone()

        if row:
            conn.execute(
                "UPDATE media_cache SET use_count = use_count + 1 WHERE cache_key = ?",
                (cache_key,)
            )
            conn.commit()
            details_logger.info("Cache hit: %s", cache_key, extra={"extra_data": _log_extra(url, cache_key)})
            return (row[0], row[1])

        return None
    except Exception as e:
        logger.error("Cache read error: %s", e)
        return None


def store(url: str, platform: str | None, file_id: str, media_type: str,
          title: str = "", file_size_mb: float = 0.0, metadata: dict | None = None) -> None:
    """Store download result in cache."""
    cache_key = _get_cache_key(url, platform, metadata)
    if not cache_key:
        logger.debug("Cannot generate cache key for %s", url)
        return

    try:
        conn = _get_db()
        conn.execute("""
            INSERT INTO media_cache
            (cache_key, file_id, media_type, platform, title, file_size_mb)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                file_id = excluded.file_id,
                media_type = excluded.media_type,
                platform = excluded.platform,
                title = excluded.title,
                file_size_mb = excluded.file_size_mb
        """, (cache_key, file_id, media_type, platform, title, file_size_mb))
        conn.commit()
        details_logger.info("Cached: %s", cache_key, extra={"extra_data": _log_extra(url, cache_key)})
    except Exception as e:
        logger.error("Cache write error: %s", e)


def get_stats() -> dict:
    """Return cache statistics."""
    try:
        conn = _get_db()
        row = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(file_size_mb), 0)
            FROM media_cache
        """).fetchone()
        return {
            "total_entries": row[0],
            "total_size_mb": round(row[1], 2),
        }
    except Exception as e:
        logger.error("Cache stats error: %s", e)
        return {"total_entries": 0, "total_size_mb": 0}


def clear_redirect_cache():
    """Clear in-memory redirect cache. For testing."""
    _redirect_cache.clear()


def cleanup_older_than(days: int = 30) -> int:
    """Remove cache entries older than specified days. Returns count removed."""
    try:
        conn = _get_db()
        cursor = conn.execute(
            "DELETE FROM media_cache WHERE created_at < datetime('now', '-' || ? || ' days')",
            (days,)
        )
        conn.commit()
        removed = cursor.rowcount
        if removed:
            logger.info("Cache cleanup: removed %d entries older than %d days", removed, days)
        return removed
    except Exception as e:
        logger.error("Cache cleanup error: %s", e)
        return 0
