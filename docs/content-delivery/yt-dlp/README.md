# yt-dlp Integration

Video downloads using yt-dlp as a subprocess.

## Overview

yt-dlp is called as a subprocess (not imported as a Python library). This keeps it independently upgradable.

## Subprocess Calls

```python
# src/downloader.py
def download_video(url: str, output_path: str, max_size_mb: int = 50, platform: str = "") -> bool:
    """Download video using yt-dlp."""
    ytdlp = _find_ytdlp()
    max_bytes = max_size_mb * 1024 * 1024

    result = subprocess.run(
        [
            ytdlp,
            "-f", f"best[filesize<{max_bytes}]/best",
            "-o", output_path,
            "--no-playlist",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return True

    # Retry with worst quality
    result = subprocess.run(
        [
            ytdlp,
            "-f", "worst",
            "-o", output_path,
            "--no-playlist",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode == 0
```

## Format Selection

### Default Format
```
-f "best[filesize<{max_bytes}]/best"
```
- Prefers best quality under the Telegram file size limit (50MB = 52428800 bytes)
- Falls back to best available if no format matches the size constraint

### Retry Format
```
-f "worst"
```
- Used when default fails
- Ensures download completes

## Platform-Specific Args

### YouTube

YouTube uses `download_video()` from `src/downloader.py` directly. No platform-specific yt-dlp args needed.

### TikTok

TikTok uses `download_video()` with a platform flag that adds an extractor arg:

```python
# src/downloader.py (inside download_video)
extra_args = []
if platform == "tiktok":
    extra_args.extend(["--extractor-args", "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com"])

result = subprocess.run(
    [ytdlp, "-f", f"best[filesize<{max_bytes}]/best", "-o", output_path, "--no-playlist", *extra_args, url],
    capture_output=True, text=True, timeout=300,
)
```

### Instagram

Instagram uses `download_video()` from `src/downloader.py` directly. Cookies for gallery-dl fallback are handled separately in `src/platforms/instagram.py`.

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
