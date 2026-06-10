# Gallery-dl Supported Sites

List of platforms supported by gallery-dl.

## Overview

gallery-dl supports 100+ platforms. The bot maintains a whitelist of known-working domains.

## Generating the List

```bash
python scripts/generate_gallery_dl_domains.py
```

This script:
1. Runs `gallery-dl --version` to get version
2. Fetches supported sites from gallery-dl source
3. Writes to `src/gallery_dl_domains.py`

## Using the List

```python
# src/utils.py
from src.gallery_dl_domains import GALLERY_DL_DOMAINS

def get_gallery_dl_domains() -> set:
    """Get set of gallery-dl supported domains."""
    return GALLERY_DL_DOMAINS
```

## Checking if a Domain is Supported

```python
domain = "deviantart.com"
if domain in get_gallery_dl_domains():
    print(f"{domain} is supported")
else:
    print(f"{domain} is not supported")
```

## Common Platforms

### Image Platforms
- DeviantArt
- Pixiv
- ArtStation
- Behance
- Flickr
- 500px

### Social Media
- Twitter/X
- Reddit
- Tumblr
- Pinterest
- Mastodon

### Other
- YouTube (thumbnails only)
- Vimeo
- Dailymotion
- Bilibili

## Adding New Platforms

1. Check gallery-dl documentation for support
2. Run `python scripts/generate_gallery_dl_domains.py` to update list
3. Test with a URL from the new platform
4. If works, domain is automatically included

## Troubleshooting

### Domain Not in Whitelist
- Run `python scripts/generate_gallery_dl_domains.py`
- Check if gallery-dl supports the platform
- If not, request support upstream

### gallery-dl Fails
- Check if authentication is needed
- Check if format is supported
- Check logs for error details

## Related

- [Fallback Strategy](fallback-strategy.md) - How fallback works
- [gallery-dl Integration](README.md) - General gallery-dl docs
