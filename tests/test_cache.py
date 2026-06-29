import os
from cache import (
    get_cached,
    store,
    _extract_tiktok_id,
    _extract_youtube_id,
    _extract_instagram_shortcode,
)


def test_cache_creates_database_file(tmp_path, monkeypatch):
    """Cache module creates SQLite database on first use."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    # Force re-initialization
    import cache
    cache._db_path = None

    # Trigger DB creation by calling any function
    get_cached("https://example.com", "test")

    db_file = tmp_path / "media_cache.db"
    assert db_file.exists()


def test_extract_tiktok_id_from_full_url():
    """Extract video ID from tiktok.com/@user/video/ID URL."""
    url = "https://www.tiktok.com/@ghosttunnel.vpn/video/7634892654269959446?_r=1&u_code=test"
    assert _extract_tiktok_id(url) == "7634892654269959446"


def test_extract_tiktok_id_from_short_url():
    """Short vt.tiktok.com URLs return None (need metadata)."""
    url = "https://vt.tiktok.com/ZSQqy1R4y/"
    assert _extract_tiktok_id(url) is None


def test_extract_youtube_id_from_watch_url():
    """Extract video ID from youtube.com/watch?v=ID."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
    assert _extract_youtube_id(url) == "dQw4w9WgXcQ"


def test_extract_youtube_id_from_short_url():
    """Extract video ID from youtu.be/ID."""
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert _extract_youtube_id(url) == "dQw4w9WgXcQ"


def test_extract_instagram_shortcode():
    """Extract shortcode from instagram.com/p/SHORTCODE/."""
    url = "https://www.instagram.com/p/ABC123XYZ/"
    assert _extract_instagram_shortcode(url) == "ABC123XYZ"


def test_extract_instagram_shortcode_from_reel():
    """Extract shortcode from instagram.com/reel/SHORTCODE/."""
    url = "https://www.instagram.com/reel/ABC123XYZ/"
    assert _extract_instagram_shortcode(url) == "ABC123XYZ"
