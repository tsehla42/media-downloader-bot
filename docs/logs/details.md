# Details Logging

The `request-details.jsonl` file contains intermediate download steps and technical details.

## Purpose

Captures the detailed steps during media download:
- yt-dlp subprocess calls and arguments
- Download attempts and retries
- Gallery-dl fallback attempts
- File size checks and validation

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
