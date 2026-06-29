import os
import pytest
from cache import get_cached, store, _get_db


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
