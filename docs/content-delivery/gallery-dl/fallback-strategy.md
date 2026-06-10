# Fallback Strategy

How the bot falls back to gallery-dl when yt-dlp fails.

## Overview

The bot uses a fallback strategy:
1. Try yt-dlp first (primary)
2. If fails, try gallery-dl (fallback)
3. If both fail, send error

## When Fallback Happens

### yt-dlp Failures
- Download failed (network error, rate limit, etc.)
- Format not available
- File too large

### Platform Not Supported by yt-dlp
- Platforms not in `SUPPORTED_PLATFORMS`
- Platforms where yt-dlp doesn't work well

## Fallback Logic

```python
# src/handlers.py
@with_request_logging
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle URL message."""
    # Authorization check
    if not is_authorized(update):
        return

    text = update.message.text.strip()
    urls = extract_urls(text)

    # Split into supported (YT/TT/IG) and unsupported URLs
    supported_urls = [url for url in urls if detect_platform(url)]
    unsupported_urls = [url for url in urls if not detect_platform(url)]

    # Platform-specific handlers
    for url in supported_urls:
        await _download_and_send(update, context, url)

    # Filter unsupported URLs against gallery-dl domain whitelist
    gallery_dl_domains = get_gallery_dl_domains()
    unsupported_urls = [url for url in unsupported_urls if extract_domain(url) in gallery_dl_domains]

    # Process remaining unsupported URLs via gallery-dl fallback
    for url in unsupported_urls:
        await handle_gallery_dl_fallback(update, context, url)
```

## Domain Whitelist Check

Before trying gallery-dl, bot checks if domain is in whitelist:

```python
# src/handlers.py
async def handle_gallery_dl_fallback(url: str, request_id: str) -> str:
    """Try gallery-dl as fallback."""
    domain = extract_domain(url)
    
    # Check whitelist
    if domain not in get_gallery_dl_domains():
        details_logger.info("gallery-dl: domain not in whitelist", extra={
            "url": url,
            "domain": domain,
            "request_id": request_id
        })
        return None
    
    # Try download
    # ...
```

## Image vs Video Detection

gallery-dl downloads files. Bot detects type by extension using `glob.glob()`:

```python
# src/downloader.py (inside download_gallery_dl_images)
images = sorted(
    glob.glob(f"{output_dir}/**/*.jpg", recursive=True)
    + glob.glob(f"{output_dir}/**/*.jpeg", recursive=True)
    + glob.glob(f"{output_dir}/**/*.png", recursive=True)
    + glob.glob(f"{output_dir}/**/*.webp", recursive=True)
)

# src/downloader.py (inside download_gallery_dl_video)
video_extensions = ["*.mp4", "*.webm", "*.mkv", "*.mov"]
videos = []
for ext in video_extensions:
    videos.extend(glob.glob(f"{output_dir}/**/{ext}", recursive=True))
# Returns the largest video found
return max(videos, key=os.path.getsize) if videos else None
```

## Error Handling

### gallery-dl Fails
- Bot sends error to user
- Logs failure to request-details.jsonl

### No Files Downloaded
- Bot sends "Unsupported platform" message
- Logs as expected failure

## Logging

Fallback attempts are logged:

```json
{
  "event": "gallery_dl_attempt",
  "url": "https://example.com/image.jpg",
  "domain": "example.com",
  "request_id": "abc123",
  "success": true
}
```

## Related

- [Supported Sites](supported-sites.md) - Gallery-dl supported platforms
- [yt-dlp Integration](../yt-dlp/) - Primary downloads
