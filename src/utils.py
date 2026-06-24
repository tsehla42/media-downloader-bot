"""Utility functions for URL validation, directory management, and file cleanup."""

import os
import re
import shutil

URL_PATTERN = re.compile(r"https?://\S+")


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


def get_gallery_dl_domains() -> frozenset[str]:
    """Get gallery-dl supported domains. Auto-generates if missing."""
    try:
        from gallery_dl_domains import GALLERY_DL_DOMAINS
        return GALLERY_DL_DOMAINS
    except ImportError:
        # Try to generate the file
        try:
            import subprocess
            import sys
            from pathlib import Path
            script = str(Path(__file__).resolve().parent.parent / "scripts" / "python" / "generate_gallery_dl_domains.py")
            subprocess.run(
                [sys.executable, script],
                timeout=30,
                check=True,
                capture_output=True,
            )
            from gallery_dl_domains import GALLERY_DL_DOMAINS
            return GALLERY_DL_DOMAINS
        except Exception:
            return frozenset()


def get_ytdlp_domains() -> frozenset[str]:
    """Get yt-dlp supported domains. Auto-generates if missing."""
    try:
        from ytdlp_domains import YTDLP_DOMAINS
        return YTDLP_DOMAINS
    except ImportError:
        # Try to generate the file
        try:
            import subprocess
            import sys
            from pathlib import Path
            script = str(Path(__file__).resolve().parent.parent / "scripts" / "python" / "generate_ytdlp_domains.py")
            subprocess.run(
                [sys.executable, script],
                timeout=30,
                check=True,
                capture_output=True,
            )
            from ytdlp_domains import YTDLP_DOMAINS
            return YTDLP_DOMAINS
        except Exception:
            return frozenset()
