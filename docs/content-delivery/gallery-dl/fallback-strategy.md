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
async def handle_url(update: Update, url: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle URL message."""
    platform = detect_platform(url)
    
    # Try platform-specific handler
    if platform in ["youtube", "ytmusic"]:
        await handle_youtube(update, url, context)
    elif platform == "tiktok":
        await handle_tiktok(update, url, context)
    elif platform == "instagram":
        await handle_instagram(update, url, context)
    else:
        # Unknown platform - try gallery-dl fallback
        result = await handle_gallery_dl_fallback(url, request_id)
        if result:
            await send_media(update, result, context)
        else:
            await update.message.reply_text("Unsupported platform")
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

gallery-dl downloads files. Bot detects type by extension:

```python
# src/utils.py
def find_downloaded_files(url: str) -> list:
    """Find files downloaded by gallery-dl."""
    files = []
    for file in os.listdir(DOWNLOAD_DIR):
        if file.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            files.append(os.path.join(DOWNLOAD_DIR, file))
        elif file.endswith(('.mp4', '.webm', '.mkv')):
            files.append(os.path.join(DOWNLOAD_DIR, file))
    return files
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
