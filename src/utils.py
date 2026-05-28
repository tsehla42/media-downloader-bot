import os
import re
import shutil
from urllib.parse import urlparse

SUPPORTED_PLATFORMS = {
    "youtube": ["youtube.com", "youtu.be"],
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com", "douyin.com"],
    "instagram": ["instagram.com"],
}

URL_PATTERN = re.compile(r"https?://\S+")


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


def is_valid_url(text: str) -> bool:
    """Check if text contains a valid HTTP(S) URL."""
    return URL_PATTERN.search(text.strip()) is not None


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP(S) URLs from text."""
    return URL_PATTERN.findall(text)


def ensure_download_dir(path: str) -> str:
    """Create download directory if it doesn't exist, return path."""
    os.makedirs(path, exist_ok=True)
    return path


def cleanup_file(path: str) -> None:
    """Remove a file if it exists."""
    if path and os.path.isfile(path):
        os.remove(path)


def cleanup_dir(path: str) -> None:
    """Remove a directory and its contents if it exists."""
    if path and os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
