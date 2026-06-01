import glob
import json
import logging
import os
import re
import subprocess
import shutil
import sys
import tempfile

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_MB = 50


def _find_ytdlp() -> str:
    """Find yt-dlp binary path."""
    path = shutil.which("yt-dlp")
    if not path:
        raise FileNotFoundError(
            "yt-dlp not found. Install with: pip install yt-dlp"
        )
    return path


def _find_gallery_dl() -> str | None:
    """Find gallery-dl binary path.

    Checks shutil.which first, then falls back to the venv's bin/ directory
    (needed when VS Code or Docker strips the venv from PATH).
    """
    path = shutil.which("gallery-dl")
    if path:
        return path

    # Fallback: look next to the running Python executable (venv bin/ dir)
    python_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(python_dir, "gallery-dl")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate

    return None


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
    """Download images from carousel/gallery post using gallery-dl.

    Falls back to yt-dlp thumbnail extraction if gallery-dl is unavailable.
    Returns list of file paths.
    """
    # Try gallery-dl first (handles carousels well with cookies)
    from config import INSTAGRAM_COOKIES
    images = download_instagram_gallery_dl(url, output_dir, INSTAGRAM_COOKIES)
    if images:
        return images

    # Fallback: yt-dlp can extract thumbnails from video posts
    ytdlp = _find_ytdlp()
    os.makedirs(output_dir, exist_ok=True)
    result = subprocess.run(
        [
            ytdlp,
            "-o", f"{output_dir}/%(id)s.%(ext)s",
            "--write-thumbnail",
            "--no-download",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        return []
    return sorted(glob.glob(f"{output_dir}/*.[jp][pn]g") + glob.glob(f"{output_dir}/*.webp"))


def download_instagram_gallery_dl(url: str, output_dir: str, cookies: str = "") -> list[str]:
    """Download images from Instagram using gallery-dl.

    Requires gallery-dl binary and a cookies.txt file for authentication.
    Returns list of downloaded file paths, or empty list on failure.
    """
    if not cookies:
        logger.warning("gallery-dl: no cookies path provided")
        return []

    gd_path = _find_gallery_dl()
    if not gd_path:
        logger.warning("gallery-dl: binary not found in PATH")
        return []

    # Resolve to absolute path so subprocess finds it regardless of cwd
    cookies = os.path.abspath(cookies)
    if not os.path.isfile(cookies):
        logger.warning("gallery-dl: cookies file not found: %s", cookies)
        return []

    os.makedirs(output_dir, exist_ok=True)
    output_dir = os.path.abspath(output_dir)

    logger.info("gallery-dl: downloading %s to %s (cookies: %s)", url, output_dir, cookies)
    result = subprocess.run(
        [
            gd_path,
            "-d", output_dir,
            "--cookies", cookies,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        logger.warning("gallery-dl: failed (code %d): %s", result.returncode, result.stderr[:200])
        return []

    images = sorted(
        glob.glob(f"{output_dir}/**/*.jpg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.jpeg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.png", recursive=True)
        + glob.glob(f"{output_dir}/**/*.webp", recursive=True)
    )
    logger.info("gallery-dl: found %d images", len(images))
    return images


def download_instagram_image(url: str, output_path: str) -> bool:
    """Download a single image from an Instagram post using instaloader.

    Used as fallback when yt-dlp fails on image-only posts.
    """
    try:
        import instaloader
        import shutil as _shutil

        L = instaloader.Instaloader(
            download_pictures=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )

        # Extract shortcode from URL (e.g., /p/ABC123/ or /reel/ABC123/)
        shortcode = None
        match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
        if match:
            shortcode = match.group(1)

        if not shortcode:
            return False

        post = instaloader.Post.from_shortcode(L.context, shortcode)

        # Only handle single image posts (not carousels or videos)
        if post.typename == "GraphSidecar":
            return False  # Carousels are handled elsewhere

        if not post.is_video:
            # Download the image
            with tempfile.TemporaryDirectory() as tmpdir:
                L.download_post(post, target=tmpdir)
                # Find the downloaded image file
                for f in os.listdir(tmpdir):
                    if f.endswith(('.jpg', '.jpeg', '.png', '.webp')) and not f.endswith('_caption.jpg'):
                        src = os.path.join(tmpdir, f)
                        _shutil.copy2(src, output_path)
                        return os.path.isfile(output_path)
            return False

        return False  # Videos are handled by yt-dlp
    except Exception:
        return False
