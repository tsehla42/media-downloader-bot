import os
from cache import (
    get_cached,
    store,
    get_stats,
    cleanup_older_than,
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
    cache._conn = None

    # Trigger DB creation by calling store (generates a valid cache key)
    store("https://www.tiktok.com/@user/video/1234567890", "tiktok", "id", "video")

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


def test_store_and_retrieve(monkeypatch, tmp_path):
    """Store a value and retrieve it."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    url = "https://www.tiktok.com/@user/video/1234567890"
    store(url, "tiktok", "test_file_id_123", "video", "Test Video", 5.0)

    result = get_cached(url, "tiktok")
    assert result is not None
    file_id, media_type = result
    assert file_id == "test_file_id_123"
    assert media_type == "video"


def test_cache_miss(monkeypatch, tmp_path):
    """Cache miss returns None."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    result = get_cached("https://www.tiktok.com/@user/video/9999999999", "tiktok")
    assert result is None


def test_cache_overwrite(monkeypatch, tmp_path):
    """Storing same key twice overwrites previous value."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    url = "https://www.tiktok.com/@user/video/1234567890"
    store(url, "tiktok", "old_file_id", "video", "Old", 5.0)
    store(url, "tiktok", "new_file_id", "video", "New", 6.0)

    result = get_cached(url, "tiktok")
    assert result[0] == "new_file_id"


def test_cache_with_metadata_key(monkeypatch, tmp_path):
    """Cache works with metadata-based keys."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    url = "https://vt.tiktok.com/ZSQqy1R4y/"
    metadata = {"id": "7650818360782884114", "title": "test"}
    store(url, "tiktok", "file_id_456", "video", "Test", 5.0, metadata)

    result = get_cached(url, "tiktok", metadata)
    assert result is not None
    assert result[0] == "file_id_456"


def test_cache_increments_use_count(monkeypatch, tmp_path):
    """Cache increments use_count on each retrieval."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    url = "https://www.tiktok.com/@user/video/1234567890"
    store(url, "tiktok", "test_id", "video", "Test", 5.0)

    get_cached(url, "tiktok")
    get_cached(url, "tiktok")

    conn = cache._get_db()
    row = conn.execute("SELECT use_count FROM media_cache WHERE cache_key = ?",
                       ("tiktok:1234567890",)).fetchone()
    assert row[0] == 3  # 1 from store + 2 from get_cached


def test_cache_preserves_use_count_on_overwrite(monkeypatch, tmp_path):
    """Storing same key preserves use_count."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    url = "https://www.tiktok.com/@user/video/1234567890"
    store(url, "tiktok", "old_id", "video", "Old", 5.0)
    get_cached(url, "tiktok")  # Increment use_count to 2
    get_cached(url, "tiktok")  # Increment use_count to 3

    store(url, "tiktok", "new_id", "video", "New", 6.0)  # Overwrite

    result = get_cached(url, "tiktok")
    assert result[0] == "new_id"  # New file_id

    conn = cache._get_db()
    row = conn.execute("SELECT use_count FROM media_cache WHERE cache_key = ?",
                       ("tiktok:1234567890",)).fetchone()
    assert row[0] == 4  # 3 from before + 1 from this get_cached


def test_get_stats(monkeypatch, tmp_path):
    """Stats returns correct counts."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    store("https://www.tiktok.com/@user/video/1", "tiktok", "id1", "video", "V1", 1.0)
    store("https://www.tiktok.com/@user/video/2", "tiktok", "id2", "video", "V2", 2.0)

    stats = get_stats()
    assert stats["total_entries"] == 2
    assert stats["total_size_mb"] == 3.0


def test_get_stats_empty_cache(monkeypatch, tmp_path):
    """Stats on empty cache returns zeros."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    stats = get_stats()
    assert stats["total_entries"] == 0
    assert stats["total_size_mb"] == 0


def test_cleanup_older_than(monkeypatch, tmp_path):
    """Cleanup removes entries older than specified days."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    conn = cache._get_db()
    conn.execute("""
        INSERT INTO media_cache (cache_key, file_id, media_type, created_at)
        VALUES ('old:key', 'old_id', 'video', datetime('now', '-31 days'))
    """)
    conn.execute("""
        INSERT INTO media_cache (cache_key, file_id, media_type, created_at)
        VALUES ('new:key', 'new_id', 'video', datetime('now'))
    """)
    conn.commit()

    removed = cleanup_older_than(30)
    assert removed == 1

    stats = get_stats()
    assert stats["total_entries"] == 1


def test_cleanup_older_than_removes_nothing(monkeypatch, tmp_path):
    """Cleanup with no old entries removes nothing."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    import cache
    cache._db_path = None
    cache._conn = None

    store("https://www.tiktok.com/@user/video/1", "tiktok", "id1", "video", "V1", 1.0)

    removed = cleanup_older_than(30)
    assert removed == 0

    stats = get_stats()
    assert stats["total_entries"] == 1
