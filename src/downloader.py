import json
import os
import re
import subprocess
import shutil
import urllib.request

MAX_FILE_SIZE_MB = 50


def _find_ytdlp() -> str:
    """Find yt-dlp binary path."""
    path = shutil.which("yt-dlp")
    if not path:
        raise FileNotFoundError(
            "yt-dlp not found. Install with: pip install yt-dlp"
        )
    return path


def get_metadata(url: str) -> dict | None:
    """Get video metadata via yt-dlp --dump-json."""
    try:
        ytdlp = _find_ytdlp()
        result = subprocess.run(
            [ytdlp, "--dump-json", "--no-download", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def download_video(url: str, output_path: str, max_size_mb: int = MAX_FILE_SIZE_MB, platform: str = "") -> bool:
    """Download video, retrying with lower quality if too large."""
    ytdlp = _find_ytdlp()
    max_bytes = max_size_mb * 1024 * 1024

    extra_args = []
    if platform == "tiktok":
        extra_args.extend(["--extractor-args", "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com"])

    result = subprocess.run(
        [
            ytdlp,
            "-f", f"best[filesize<{max_bytes}]/best",
            "-o", output_path,
            "--no-playlist",
            *extra_args,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return True

    result = subprocess.run(
        [
            ytdlp,
            "-f", "worst",
            "-o", output_path,
            "--no-playlist",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode == 0


def download_audio(url: str, output_path: str) -> bool:
    """Extract audio as MP3."""
    ytdlp = _find_ytdlp()
    result = subprocess.run(
        [
            ytdlp,
            "--extract-audio",
            "--audio-format", "mp3",
            "-o", output_path,
            "--no-playlist",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode == 0


def download_images(url: str, output_dir: str) -> list[str]:
    """Download images from carousel/gallery post. Returns list of file paths."""
    ytdlp = _find_ytdlp()
    os.makedirs(output_dir, exist_ok=True)
    result = subprocess.run(
        [
            ytdlp,
            "-o", f"{output_dir}/%(id)s.%(ext)s",
            "--write-images",
            "--no-download",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return []
    import glob
    return sorted(glob.glob(f"{output_dir}/*.[jp][pn]g") + glob.glob(f"{output_dir}/*.webp"))


def download_instagram_image(url: str, output_path: str) -> bool:
    """Download a single image from an Instagram post by scraping og:image meta tag.

    Used as fallback when yt-dlp fails on image-only posts.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # Try og:image meta tag first
        match = re.search(r'<meta\s+(?:property|name)="og:image"\s+content="([^"]+)"', html)
        if not match:
            match = re.search(r'<meta\s+content="([^"]+)"\s+(?:property|name)="og:image"', html)

        if match:
            image_url = match.group(1).replace("&amp;", "&")
            urllib.request.urlretrieve(image_url, output_path)
            return os.path.isfile(output_path)

        return False
    except Exception:
        return False
