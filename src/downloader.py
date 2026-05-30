import json
import os
import re
import subprocess
import shutil
import tempfile

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
