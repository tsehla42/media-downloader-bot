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
6. Bot uploads file to Telegram
7. Bot cleans up temp files

## Platform Detection

```python
# src/platforms/__init__.py
SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be", "m.youtube.com"],
    "ytmusic": ["music.youtube.com"],
    "tiktok": ["tiktok.com", "vm.tiktok.com"],
    "instagram": ["instagram.com", "instagr.am"],
}

def detect_platform(url: str) -> str:
    """Detect platform from URL."""
    domain = extract_domain(url)
    for platform, domains in SUPPORTED_PLATFORMS.items():
        if domain in domains:
            return platform
    return "unknown"
```

## File Size Limits

- Telegram limit: 50MB for bots
- Bot checks file size before uploading
- If too large, tries lower quality
- If still too large, sends error message

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
