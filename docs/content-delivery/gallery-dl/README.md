# gallery-dl Integration

Image downloads and fallback using gallery-dl.

## Overview

gallery-dl is used for:
1. Fallback when yt-dlp fails
2. Downloading images from platforms
3. Supporting 100+ platforms not natively supported

## Subprocess Calls

```python
# src/downloader.py
def download_gallery_dl_images(url: str, output_dir: str, cookies: str = "") -> list[str]:
    """Download images using gallery-dl."""
    gd_path = _find_gallery_dl()
    if not gd_path:
        return []

    os.makedirs(output_dir, exist_ok=True)
    output_dir = os.path.abspath(output_dir)

    cmd = [gd_path, "-d", output_dir]
    if cookies:
        cookies = os.path.abspath(cookies)
        if not os.path.isfile(cookies):
            return []
        cmd.extend(["--cookies", cookies])
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        return []

    images = sorted(
        glob.glob(f"{output_dir}/**/*.jpg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.jpeg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.png", recursive=True)
        + glob.glob(f"{output_dir}/**/*.webp", recursive=True)
    )
    return images
```

## Domain Whitelist

gallery-dl supports 100+ platforms. The bot maintains a whitelist of known-working domains.

```python
# src/utils.py
def get_gallery_dl_domains() -> frozenset[str]:
    """Get gallery-dl supported domains. Auto-generates if missing."""
    try:
        from gallery_dl_domains import GALLERY_DL_DOMAINS
        return GALLERY_DL_DOMAINS
    except ImportError:
        # Try to generate the file via scripts/python/generate_gallery_dl_domains.py
        # Falls back to empty frozenset on failure
        ...
```

### Generating Domain List

```bash
python scripts/python/generate_gallery_dl_domains.py
```

This fetches the list from gallery-dl and writes to `src/gallery_dl_domains.py`.

## Fallback Strategy

When yt-dlp fails, bot tries gallery-dl:

```python
# src/handlers.py
async def handle_gallery_dl_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> bool:
    """Try gallery-dl for unsupported platforms. Silent on failure."""
    reply_params = {"message_id": update.message.message_id}

    # Try images first
    images = download_gallery_dl_images(url, out_dir, "")
    if images:
        total_size = await send_images(update.message, images, reply_params)
        return True

    # Try video
    video = download_gallery_dl_video(url, out_dir)
    if video:
        with open(video, "rb") as f:
            await update.message.reply_video(video=f, reply_parameters=reply_params)
        return True

    return False
```

## Documentation

- [Fallback Strategy](fallback-strategy.md) - Fallback logic and domain whitelist
- [Supported Sites](supported-sites.md) - Gallery-dl supported platforms

## Related

- [yt-dlp Integration](../yt-dlp/) - Primary video downloads
- [Content Delivery](../README.md) - Overview
