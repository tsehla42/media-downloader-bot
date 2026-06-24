# Details Logging

The `request-details.jsonl` file contains intermediate download steps and technical details.

## Purpose

Captures the detailed steps during media download:
- yt-dlp subprocess calls and arguments
- Download attempts and retries
- Gallery-dl fallback attempts with stderr on failure
- File size checks and validation

## Extra Fields

These fields appear in request-details.jsonl entries when present:

| Field | Type | When |
|-------|------|------|
| `request_id` | string | All entries — links to requests.jsonl |
| `url` | string | All entries |
| `platform` | string | TikTok/Instagram/YouTube entries |
| `yt_dlp_stderr` | string | yt-dlp failure or retry — full stderr output |
| `gallery_dl_stderr` | string | gallery-dl failure — full stderr output |

## Events

### download_video: running yt-dlp
```json
{
  "timestamp": "2026-06-10T20:41:50.047014+03:00",
  "level": "INFO",
  "message": "download_video: running yt-dlp",
  "url": "https://vt.tiktok.com/ZS9Gg6dGp/",
  "request_id": "8e314411"
}
```

### download_video: yt-dlp failed (with stderr)
```json
{
  "timestamp": "2026-06-24T19:36:40.055860+03:00",
  "level": "WARNING",
  "message": "download_video: yt-dlp failed (code 1)",
  "url": "https://vt.tiktok.com/ZSCNN3Qh7/",
  "request_id": "cf159b18",
  "platform": "tiktok",
  "yt_dlp_stderr": "WARNING: [generic] Falling back on generic information extractor\nERROR: Unsupported URL: https://www.tiktok.com/@aluushhh/photo/7653930900106874132"
}
```

### gallery-dl: failed (with stderr)
```json
{
  "timestamp": "2026-06-24T19:36:41.579074+03:00",
  "level": "WARNING",
  "message": "gallery-dl: failed (code 4)",
  "url": "https://vt.tiktok.com/ZSCNN3Qh7/",
  "request_id": "cf159b18",
  "gallery_dl_stderr": "[tiktok][error] Failed to extract post (HttpError: '403 Forbidden')"
}
```

### download_video: retrying with lower quality
```json
{
  "timestamp": "2026-06-10T20:41:52.808687+03:00",
  "level": "INFO",
  "message": "download_video: retrying with lower quality",
  "url": "https://vt.tiktok.com/ZS9Gg6dGp/",
  "request_id": "8e314411"
}
```

### download_video: yt-dlp ok
```json
{
  "timestamp": "2026-06-10T20:42:00.042760+03:00",
  "level": "INFO",
  "message": "download_video: yt-dlp ok",
  "url": "https://vt.tiktok.com/ZS9Gg6dGp/",
  "request_id": "8e314411"
}
```

### download_video: yt-dlp ok (fallback)
```json
{
  "timestamp": "2026-06-10T20:42:00.042760+03:00",
  "level": "INFO",
  "message": "download_video: yt-dlp ok (fallback)",
  "url": "https://vt.tiktok.com/ZS9Gg6dGp/",
  "request_id": "8e314411"
}
```

## Logger

Details are logged via `details_logger` in `src/logging_config.py`:

```python
from src.logging_config import details_logger

details_logger.info("download_video: running yt-dlp", extra={"url": url, "request_id": request_id})
```

## Related

- [Request Lifecycle](requests.md) - High-level request events
- [Service Logging](service.md) - Bot events
