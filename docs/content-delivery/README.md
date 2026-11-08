# Content Delivery

How the bot downloads and delivers media to users.

## Overview

The bot uses two main tools for downloading media:
- **yt-dlp** - Primary tool for video downloads (YouTube, TikTok, Instagram)
- **gallery-dl** - Fallback for images and unsupported platforms

## Download Flow

1. User sends URL
2. Bot detects platform
3. Bot routes to appropriate handler:
   - YouTube/YouTube Music → `platforms/youtube.py`
   - TikTok → `platforms/tiktok.py`
   - Instagram → `platforms/instagram.py`
   - Other → `handle_gallery_dl_fallback()`
4. Handler calls downloader functions in `src/downloader.py`
5. Downloader executes yt-dlp or gallery-dl as subprocess
6. On failure, raises `DownloadError` with user-facing message and raw error for logging
7. Bot uploads file to Telegram
8. Bot cleans up temp files

## Platform Detection

```python
# src/platforms/__init__.py
SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be", "music.youtube.com"],
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com", "douyin.com"],
    "instagram": ["instagram.com"],
}

def detect_platform(url: str) -> str | None:
    """Detect which platform a URL belongs to."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host = re.sub(r"^www\.", "", host)
        for platform, domains in SUPPORTED_PLATFORMS.items():
            if host in domains:
                return platform
    except Exception:
        pass
    return None
```

## File Size Limits

- Telegram limit: 50MB for bots
- Bot checks file size before uploading
- If too large, tries lower quality
- If still too large, sends error message

## Video Streaming

For Telegram to stream a video (play inline while downloading) instead of showing a download tile, three things must be true:

1. **Faststart** — `moov` before `mdat`, applied after download via `_apply_faststart()` (moves the atom without re-encoding).
2. **H.264 codec** — chosen by the codec-priority format selector (`ext=mp4` does not imply H.264; VP9/AV1 won't play on every client).
3. **Send metadata** — `supports_streaming=True` **plus** `duration`, `width`, `height` on every `sendVideo`.

All video sends pass all three. This applies to every path: direct reply, gallery-dl fallback, guest-mode storage upload, and YouTube Music callbacks.

The metadata comes from `telegram_utils.probe_video_metadata(path)` (an `ffprobe` call that returns `{}` on any failure, so a probe error never blocks a send). It is required because Telegram only auto-probes files under ~10MB — above that, omitting the metadata makes the server store `0/0/0`, so the client shows a `0:00` download tile and Android refuses to stream even though the file itself is perfect faststart H.264. python-telegram-bot does not probe on your behalf: `send_video` passes through only what it is given.

## Temporary Files

- Downloads stored in `DOWNLOAD_DIR` (default: `/tmp/bot-downloads/`)
- Cleaned up after upload
- No persistent storage

## Documentation

- [yt-dlp](yt-dlp/) - Video downloads
  - [YouTube](yt-dlp/youtube.md) - YouTube-specific handling
  - [TikTok](yt-dlp/tiktok.md) - TikTok-specific handling
  - [Instagram](yt-dlp/instagram.md) - Instagram-specific handling
- [gallery-dl](gallery-dl/) - Image downloads and fallbacks
  - [Fallback Strategy](gallery-dl/fallback-strategy.md) - Fallback logic
  - [Supported Sites](gallery-dl/supported-sites.md) - Gallery-dl supported platforms

## Related

- [Request Logging](../logs/requests.md) - How downloads are logged
- [Details Logging](../logs/details.md) - Intermediate download steps
