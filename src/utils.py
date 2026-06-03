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
