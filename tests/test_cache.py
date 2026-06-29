import os
from cache import (
    get_cached,
    store,
    _extract_tiktok_id,
    _extract_youtube_id,
    _extract_instagram_shortcode,
    _get_cache_key,
    _metadata_hash,
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


def test_get_cache_key_tiktok_full_url():
    """TikTok full URL generates tiktok:ID key."""
    url = "https://www.tiktok.com/@user/video/7634892654269959446"
    assert _get_cache_key(url, "tiktok") == "tiktok:7634892654269959446"


def test_get_cache_key_tiktok_short_url_no_metadata():
    """TikTok short URL without metadata returns None."""
    url = "https://vt.tiktok.com/ZSQqy1R4y/"
    assert _get_cache_key(url, "tiktok") is None


def test_get_cache_key_tiktok_short_url_with_metadata():
    """TikTok short URL with metadata generates tiktok:ID key."""
    url = "https://vt.tiktok.com/ZSQqy1R4y/"
    metadata = {"id": "7650818360782884114", "title": "test"}
    assert _get_cache_key(url, "tiktok", metadata) == "tiktok:7650818360782884114"


def test_get_cache_key_youtube():
    """YouTube URL generates youtube:ID key."""
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert _get_cache_key(url, "youtube") == "youtube:dQw4w9WgXcQ"


def test_get_cache_key_instagram():
    """Instagram URL generates instagram:SHORTCODE key."""
    url = "https://www.instagram.com/p/ABC123XYZ/"
    assert _get_cache_key(url, "instagram") == "instagram:ABC123XYZ"


def test_get_cache_key_unknown_platform_with_metadata():
    """Unknown platform uses metadata hash."""
    url = "https://example.com/video"
    metadata = {"title": "Test Video", "duration": 120, "uploader": "testuser"}
    key = _get_cache_key(url, None, metadata)
    assert key.startswith("meta:")
    assert len(key) == 13  # "meta:" + 8 char hash


def test_get_cache_key_unknown_platform_no_metadata():
    """Unknown platform without metadata returns None."""
    url = "https://example.com/video"
    assert _get_cache_key(url, None) is None


def test_metadata_hash_deterministic():
    """Same metadata produces same hash."""
    metadata = {"title": "Test", "duration": 60, "uploader": "user"}
    hash1 = _metadata_hash(metadata)
    hash2 = _metadata_hash(metadata)
    assert hash1 == hash2


def test_metadata_hash_different_for_different_content():
    """Different metadata produces different hash."""
    meta1 = {"title": "Video A", "duration": 60, "uploader": "user1"}
    meta2 = {"title": "Video B", "duration": 120, "uploader": "user2"}
    assert _metadata_hash(meta1) != _metadata_hash(meta2)
