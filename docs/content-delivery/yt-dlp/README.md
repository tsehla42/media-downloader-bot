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
    progressive_first = platform == "instagram"

    result = _run_ytdlp([
        "-f", _build_format_selector(max_bytes, progressive_first=progressive_first),
        "--merge-output-format", "mp4", "-o", output_path,
        *platform_args, url,
    ])
    if result.returncode == 0:
        _apply_faststart(output_path, ...)
        return True

    # Retry with worst quality (same platform_args applied)
    result = _run_ytdlp([
        "-f", _build_format_selector(max_bytes, worst=True, progressive_first=progressive_first),
        "--merge-output-format", "mp4", "-o", output_path,
        *platform_args, url,
    ])
    return result.returncode == 0
```

## Format Selection

Selectors are built by `_build_format_selector(max_bytes, worst=False, progressive_first=False)`
in `src/downloader.py`. `VIDEO_FORMAT_SELECTOR` (the default) and
`INSTAGRAM_FORMAT_SELECTOR` are module constants; `get_metadata()` uses
`VIDEO_FORMAT_SELECTOR` so size estimates match what `download_video()` picks.

### Branch order (default / generic)

```
1. bestvideo[ext=mp4][vcodec^=avc1][filesize<N]+bestaudio[ext=m4a]   # H.264 DASH, size-capped
2. bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]               # H.264 DASH, uncapped
3. best[ext=mp4][vcodec^=avc1][filesize<N]                           # H.264 progressive, size-capped
4. best[ext=mp4][vcodec^=avc1]                                       # H.264 progressive, uncapped
5-6. any-codec DASH merge (size-capped / uncapped)                   # AV1/VP9 fallback
7-8. any progressive (size-capped / uncapped)
9-10. best[filesize<N] / best                                        # catch-all
```

- **H.264 (avc1) first** — only codec every Telegram client decodes. iOS
  AVPlayer has no VP9 and most iPhones have no AV1; `ext=mp4` does NOT imply
  H.264 (Instagram DASH ships VP9, YouTube ships AV1 in mp4 containers).
- **Size-capped before uncapped** — yt-dlp drops formats over the limit and
  picks the best remaining, descending the quality ladder in one step
  (1080p > 50MB → 720p → 480p → ...).
- **Catch-all branches** — a low-quality or non-iOS video beats an error:
  something is always sent when a format exists.

### Instagram (`progressive_first=True`)

Instagram's H.264 rendition carries no `vcodec` metadata (codec filters skip
it) while its DASH ladder is VP9-only, so the order becomes: H.264 DASH merge
→ **bare progressive** (`best[ext=mp4]`, picks the H.264 rendition) → VP9 DASH
merge (last resort) → catch-all. Without this, the bot sent VP9 that iPhone
Telegram could not play (audio + blurred preview only).

### Retry Format

Same branch order with `worst`/`worstvideo`/`worstaudio` — used when the
first attempt fails.

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

Instagram calls `download_video(url, output_path, MAX_FILE_SIZE, platform="instagram")`,
which switches to the progressive-first selector (H.264 before VP9, see Format
Selection above). Cookies for gallery-dl fallback are handled separately in `src/platforms/instagram.py`.

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
