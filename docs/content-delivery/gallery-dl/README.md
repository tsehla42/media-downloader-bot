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
async def download_gallery_dl_images(url: str, request_id: str) -> list:
    """Download images using gallery-dl."""
    cmd = [
        "gallery-dl",
        "-d", DOWNLOAD_DIR,
        url
    ]
    
    details_logger.info("gallery-dl: running", extra={"url": url, "request_id": request_id})
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    
    if proc.returncode == 0:
        details_logger.info("gallery-dl: ok", extra={"url": url, "request_id": request_id})
        return find_downloaded_files(url)
    
    details_logger.info("gallery-dl: failed", extra={"url": url, "request_id": request_id})
    return []
```

## Domain Whitelist

gallery-dl supports 100+ platforms. The bot maintains a whitelist of known-working domains.

```python
# src/utils.py
def get_gallery_dl_domains() -> set:
    """Get set of gallery-dl supported domains."""
    # Auto-generated from gallery-dl --version
    # See scripts/generate_gallery_dl_domains.py
    return GALLERY_DL_DOMAINS
```

### Generating Domain List

```bash
python scripts/generate_gallery_dl_domains.py
```

This fetches the list from gallery-dl and writes to `src/gallery_dl_domains.py`.

## Fallback Strategy

When yt-dlp fails, bot tries gallery-dl:

```python
# src/handlers.py
async def handle_gallery_dl_fallback(url: str, request_id: str) -> str:
    """Try gallery-dl as fallback."""
    # Check if domain is in whitelist
    domain = extract_domain(url)
    if domain not in get_gallery_dl_domains():
        details_logger.info("gallery-dl: domain not in whitelist", extra={"url": url, "domain": domain})
        return None
    
    # Try images first
    images = await download_gallery_dl_images(url, request_id)
    if images:
        return images
    
    # Try video
    video = await download_gallery_dl_video(url, request_id)
    if video:
        return video
    
    return None
```

## Documentation

- [Fallback Strategy](fallback-strategy.md) - Fallback logic and domain whitelist
- [Supported Sites](supported-sites.md) - Gallery-dl supported platforms

## Related

- [yt-dlp Integration](../yt-dlp/) - Primary video downloads
- [Content Delivery](../README.md) - Overview
