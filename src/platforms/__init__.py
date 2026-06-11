# src/platforms/__init__.py
"""Platform detection and registry."""

import re
from urllib.parse import urlparse

__all__ = ["SUPPORTED_PLATFORMS", "detect_platform", "extract_domain"]

SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be", "music.youtube.com", "m.youtube.com"],
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com", "douyin.com"],
    "instagram": ["instagram.com"],
}


def detect_platform(url: str) -> str | None:
    """Detect which platform a URL belongs to."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        host = re.sub(r"^www\.", "", host)
        for platform, domains in SUPPORTED_PLATFORMS.items():
            if host in domains:
                return platform
    except Exception:
        pass
    return None


def extract_domain(url: str) -> str:
    """Extract normalized domain from URL (no www. prefix)."""
    host = urlparse(url).hostname or ""
    return re.sub(r"^www\.", "", host.lower())
