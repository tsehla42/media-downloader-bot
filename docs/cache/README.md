# Media Cache

SQLite-based cache for guest mode that stores Telegram `file_id`s to skip download+upload on repeated requests.

## How It Works

```
URL received
  → Extract platform-specific content ID from URL (instant, regex)
  → Cache hit? → return cached file_id immediately (~0ms)
  → Cache miss? → download → upload to Telegram → store file_id in cache
```

Same video shared via different URLs (e.g., different TikTok short links) maps to the same cache entry.

## Cache Key Strategy

| Platform | Key Source | Example |
|---|---|---|
| TikTok | Video ID from URL, yt-dlp metadata, HTTP redirect, or URL hash | `tiktok:7647759526040489234` |
| YouTube | `v=` param from URL | `youtube:dQw4w9WgXcQ` |
| Instagram | Shortcode from URL | `instagram:DZKGZOcPJF-` |
| Other | Hash of `title + duration + uploader` | `meta:a1b2c3d4` |

**TikTok short URLs** (`vt.tiktok.com/...`, `vm.tiktok.com/...`) don't contain video IDs. The bot resolves them using this priority:

1. **Direct URL extraction** — Full URLs like `tiktok.com/@user/video/ID` → instant regex
2. **yt-dlp metadata** — If metadata fetch succeeds, uses `metadata["id"]`
3. **HTTP redirect** — Follows the short URL redirect to get the canonical URL with video ID
4. **URL hash** — MD5 hash of the URL as fallback (different short URLs get different entries)

## Storage

- **Database:** SQLite at `$CACHE_DIR/media_cache.db` (default: `/usr/src/app/data/media_cache.db`)
- **Docker volume:** `bot-cache` — persists across container rebuilds
- **No TTL by default** — entries persist until manually cleaned

## Schema

```sql
CREATE TABLE media_cache (
    cache_key TEXT PRIMARY KEY,      -- "platform:content_id"
    file_id TEXT NOT NULL,           -- Telegram file_id
    media_type TEXT NOT NULL,        -- "video", "photo", "image"
    platform TEXT,                   -- "tiktok", "youtube", "instagram"
    title TEXT,                      -- Content title
    file_size_mb REAL,               -- File size in MB
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    use_count INTEGER DEFAULT 1      -- Incremented on each cache hit
);
```

## Inspecting the Cache

```bash
# Copy DB out of container
docker cp media-downloader-bot:/usr/src/app/data/media_cache.db /tmp/cache.db

# Query with python (sqlite3 not installed in container)
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/tmp/cache.db')
conn.row_factory = sqlite3.Row
for r in conn.execute('SELECT * FROM media_cache'):
    print(json.dumps(dict(r), indent=2))
"

# Clean up
rm /tmp/cache.db
```

## Manual Cleanup

The `cleanup_older_than(days)` function removes entries older than N days. Not called automatically — run manually when needed:

```python
from cache import cleanup_older_than
cleanup_older_than(30)  # Remove entries older than 30 days
```

## Logging

Cache operations log to `request-details.jsonl`:

```json
{"timestamp": "...", "level": "INFO", "message": "Cached: tiktok:7647759526040489234", "url": "https://vm.tiktok.com/abc", "request_id": "a1b2c3d4", "cache_key": "tiktok:7647759526040489234"}
{"timestamp": "...", "level": "INFO", "message": "Cache hit: tiktok:7647759526040489234", "url": "https://vm.tiktok.com/abc", "request_id": "e5f6g7h8", "cache_key": "tiktok:7647759526040489234"}
```

Guest request completed logs include `"cache": true/false`:

```json
{
  "event": "guest_request_completed",
  "success": true,
  "cache": true,
  "duration_ms": 479,
  "platform": "instagram"
}
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `CACHE_DIR` | `data` | Directory for SQLite database file |

## Files

| File | Purpose |
|---|---|
| `src/cache.py` | Cache module — SQLite operations, URL extraction, key generation |
| `tests/test_cache.py` | 35 unit tests |
| `tests/test_guest.py` | 8 cache integration tests |
