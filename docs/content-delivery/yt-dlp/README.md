# yt-dlp Integration

Video downloads using yt-dlp as a subprocess.

## Overview

yt-dlp is called as a subprocess (not imported as a Python library). This keeps it independently upgradable.

Common flags (`--no-playlist`, `--user-agent`) are centralized in `src/platform_args.py` as `COMMON_YTDL_ARGS`. All download functions use `_run_ytdlp()` which applies these automatically.

## Subprocess Calls

```python
# src/downloader.py
def _run_ytdlp(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """Run yt-dlp with common flags."""
    return subprocess.run(
        [_find_ytdlp(), *COMMON_YTDL_ARGS, *args],
        capture_output=True, text=True, timeout=timeout,
    )

def download_video(url, output_path, max_size_mb=50, platform=""):
    max_bytes = max_size_mb * 1024 * 1024
    platform_args = ["--referer", TIKTOK_REFERER] if platform == "tiktok" else []

    result = _run_ytdlp([
        "-f", f"best[ext=mp4][filesize<{max_bytes}]/best[ext=mp4]/best",
        "--merge-output-format", "mp4", "-o", output_path,
        *platform_args, url,
    ])
    if result.returncode == 0:
        return True

    # Retry with worst quality (same platform_args applied)
    result = _run_ytdlp([
        "-f", f"worst[ext=mp4][filesize<{max_bytes}]/worst[ext=mp4]/worst",
        "--merge-output-format", "mp4", "-o", output_path,
        *platform_args, url,
    ])
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

Platform args are defined in `src/platform_args.py` and spread into yt-dlp calls via `_run_ytdlp()`.

### YouTube

YouTube uses `download_video()` directly. No platform-specific yt-dlp args needed.

### TikTok

TikTok adds `--referer https://www.tiktok.com/` to bypass Akamai WAF (added in yt-dlp 2026.08.19 with impersonation support):

```python
# src/platform_args.py
TIKTOK_REFERER = "https://www.tiktok.com/"

# src/downloader.py (inside download_video)
platform_args = ["--referer", TIKTOK_REFERER] if platform == "tiktok" else []
result = _run_ytdlp(["-f", "...", "-o", output_path, *platform_args, url])
```

### Instagram

Instagram uses `download_video()` directly. Cookies for gallery-dl fallback are handled separately in `src/platforms/instagram.py`.

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
