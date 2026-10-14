"""Utility functions for URL validation, directory management, and file cleanup."""

import os
import re
import shutil
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import DOWNLOAD_DIR

URL_PATTERN = re.compile(r"https?://\S+")

# Known tracking parameters stripped from non-platform URLs (gallery-dl
# domains, generic sites). Load-bearing params are kept.
_TRACKER_EXACT = frozenset({
    "fbclid", "gclid", "dclid", "wbraid", "gbraid", "msclkid", "yclid",
    "twclid", "igsh", "igshid", "mc_cid", "mc_eid", "vero_id", "vero_conv",
    "ref", "ref_src", "spm", "_hsenc", "_hsmi", "mkt_tok", "s_kwcid",
    "si", "feature", "ncid", "mbid", "cmpid",
})
_TRACKER_PREFIXES = (
    "utm_", "pk_", "mtm_", "vero_", "piwik_", "matomo_", "oly_",
)

# Query params that must survive per platform. Everything else on these
# hosts is share/tracker noise (IDs live in the URL path).
_KEEP_QUERY_PARAMS: dict[str, frozenset[str]] = {
    "youtube.com": frozenset({"v", "list"}),
    "youtu.be": frozenset({"v", "list"}),
    "youtube-nocookie.com": frozenset({"v", "list"}),
    "tiktok.com": frozenset(),
    "instagram.com": frozenset({"img_index"}),
}


def _matches_host(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def _is_tracker(name: str) -> bool:
    lowered = name.lower()
    return lowered in _TRACKER_EXACT or lowered.startswith(_TRACKER_PREFIXES)


def clean_url(url: str) -> str:
    """Strip share/tracker query params from a URL, keeping it functional.

    - YouTube: keep only `v` and `list` (the rest is share noise).
    - TikTok: drop the whole query string (video ID is in the path).
    - Instagram: drop everything except `img_index` (carousel position).
    - Any other host: strip known trackers, keep everything else.
    """
    try:
        parts = urlsplit(url)
        if not parts.query or not parts.scheme.startswith("http"):
            return url
        host = parts.hostname or ""
    except ValueError:
        return url

    pairs = parse_qsl(parts.query, keep_blank_values=True)
    allowed = next(
        (keep for domain, keep in _KEEP_QUERY_PARAMS.items() if _matches_host(host, domain)),
        None,
    )
    if allowed is not None:
        kept = [kv for kv in pairs if kv[0] in allowed]
    else:
        kept = [kv for kv in pairs if not _is_tracker(kv[0])]

    if len(kept) == len(pairs):
        return url
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment)
    )


def is_valid_url(text: str) -> bool:
    """Check if text contains a valid HTTP(S) URL."""
    return URL_PATTERN.search(text.strip()) is not None


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP(S) URLs from text, cleaned of share/tracker params."""
    return [clean_url(url) for url in URL_PATTERN.findall(text)]


VIDEO_WORDS = frozenset({"video", "відео", "видео"})
AUDIO_WORDS = frozenset({"audio", "аудіо", "аудио"})


def parse_format_choice(text: str) -> str | None:
    """Parse a media format keyword from free text.

    Returns "video", "audio", "both" (both keyword families present),
    or None when no keyword is found. Matching is exact per whitespace-
    separated token, case-insensitive.
    """
    has_video = False
    has_audio = False
    for token in (text or "").lower().split():
        if token in VIDEO_WORDS:
            has_video = True
        elif token in AUDIO_WORDS:
            has_audio = True
    if has_video and has_audio:
        return "both"
    if has_video:
        return "video"
    if has_audio:
        return "audio"
    return None


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


def find_downloaded_file(base: str) -> str | None:
    """Find the first downloaded file matching mp4/webm/mkv extensions."""
    for ext in ["mp4", "webm", "mkv"]:
        candidate = f"{base}.{ext}"
        if os.path.isfile(candidate):
            return candidate
    return None


def cleanup_video_files(base: str) -> None:
    """Remove all mp4/webm/mkv variants for a download base path."""
    for ext in ["mp4", "webm", "mkv"]:
        cleanup_file(f"{base}.{ext}")


def make_video_tmp_path() -> tuple[str, str, str]:
    """Create a temp path for yt-dlp video download."""
    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    return tmp_id, output_path, base


def make_tmp_dir() -> str:
    """Create a temp directory for gallery-dl downloads."""
    tmp_id = uuid.uuid4().hex[:8]
    out_dir = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(out_dir, exist_ok=True)
    return out_dir
