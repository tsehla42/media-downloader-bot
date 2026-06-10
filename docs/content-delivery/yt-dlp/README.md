# yt-dlp Integration

Video downloads using yt-dlp as a subprocess.

## Overview

yt-dlp is called as a subprocess (not imported as a Python library). This keeps it independently upgradable.

## Subprocess Calls

```python
# src/downloader.py
async def download_video(url: str, request_id: str) -> str:
    """Download video using yt-dlp."""
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--no-check-certificates",
        "-f", "best[ext=mp4]/best",
        "--max-filesize", "50M",
        "-o", f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        url
    ]
    
    details_logger.info("download_video: running yt-dlp", extra={"url": url, "request_id": request_id})
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    
    if proc.returncode != 0:
        details_logger.info("download_video: retrying with lower quality", extra={"url": url, "request_id": request_id})
        # Retry with worst quality
        # ...
    
    details_logger.info("download_video: yt-dlp ok", extra={"url": url, "request_id": request_id})
    return output_path
```

## Format Selection

### Default Format
```
-f "best[ext=mp4]/best"
```
- Prefers MP4 format
- Falls back to best available

### Retry Format
```
-f "worst"
```
- Used when default fails
- Ensures download completes

## Platform-Specific Args

### YouTube
```python
# src/platforms/youtube.py
cmd = [
    "yt-dlp",
    "--no-warnings",
    "--no-check-certificates",
    "-f", "best[ext=mp4]/best",
    "--max-filesize", "50M",
    "-o", f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
    url
]
```

### TikTok
```python
# src/platforms/tiktok.py
cmd = [
    "yt-dlp",
    "--no-warnings",
    "--no-check-certificates",
    "-f", "best",
    "--max-filesize", "50M",
    "-o", f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
    url
]
```

### Instagram
```python
# src/platforms/instagram.py
cmd = [
    "yt-dlp",
    "--no-warnings",
    "--no-check-certificates",
    "-f", "best",
    "--max-filesize", "50M",
    "--cookies", INSTAGRAM_COOKIES,  # If configured
    "-o", f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
    url
]
```

## Error Handling

### File Too Large
```
ERROR: File is larger than max-filesize (50MB)
```
- Bot retries with lower quality
- If still too large, sends error to user

### Download Failed
```
ERROR: Unable to download video
```
- Bot tries gallery-dl fallback (if applicable)
- If no fallback, sends error to user

## Related

- [YouTube](youtube.md) - YouTube-specific handling
- [TikTok](tiktok.md) - TikTok-specific handling
- [Instagram](instagram.md) - Instagram-specific handling
- [gallery-dl](../gallery-dl/) - Fallback for images
