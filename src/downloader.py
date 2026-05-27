import json
import os
import subprocess
import shutil

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
