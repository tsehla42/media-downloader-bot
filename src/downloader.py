import glob
import json
import os
import re
import subprocess
import shutil
import sys
import tempfile

from logging_config import details_logger as logger, get_current_request_id

MAX_FILE_SIZE_MB = 50


def _log_extra(url: str, platform: str = "") -> dict:
    """Build extra fields for structured detail logging."""
    extra = {"url": url}
    request_id = get_current_request_id()
    if request_id:
        extra["request_id"] = request_id
    if platform:
        extra["platform"] = platform
    return extra


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


def _ensure_faststart(filepath: str) -> bool:
    """Move moov atom to front of MP4 for Telegram streaming.

    Uses ffmpeg to reposition the moov atom without re-encoding.
    Non-MP4 files are remuxed to MP4. Returns True on success or if
    the file is not an MP4 (nothing to do).
    """
    if not filepath.endswith(".mp4"):
        return True

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return True  # ffmpeg not available, skip

    tmp = filepath + ".faststart.mp4"
    try:
        result = subprocess.run(
            [
                ffmpeg, "-y", "-i", filepath,
                "-c", "copy", "-movflags", "+faststart",
                tmp,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and os.path.isfile(tmp):
            os.replace(tmp, filepath)
            return True
        # Cleanup on failure
        if os.path.isfile(tmp):
            os.unlink(tmp)
    except (subprocess.TimeoutExpired, OSError):
        if os.path.isfile(tmp):
            os.unlink(tmp)
    return False


def download_video(url: str, output_path: str, max_size_mb: int = MAX_FILE_SIZE_MB, platform: str = "") -> bool:
    """Download video, retrying with lower quality if too large."""
    ytdlp = _find_ytdlp()
    max_bytes = max_size_mb * 1024 * 1024
    extra = _log_extra(url, platform)

    extra_args = []
    if platform == "tiktok":
        extra_args.extend(["--extractor-args", "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com"])

    logger.info("download_video: running yt-dlp", extra=extra)
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
        _apply_faststart(output_path, extra)
        logger.info("download_video: yt-dlp ok", extra=extra)
        return True

    stderr = (result.stderr or "").strip()
    extra["yt_dlp_stderr"] = stderr
    logger.info("download_video: retrying with lower quality", extra=extra)

    result = subprocess.run(
        [
            ytdlp,
            "-f", f"worst[filesize<{max_bytes}]/worst",
            "-o", output_path,
            "--no-playlist",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        extra["yt_dlp_stderr"] = stderr
        logger.warning("download_video: yt-dlp failed (code %d)", result.returncode, extra=extra)
    else:
        _apply_faststart(output_path, extra)
        logger.info("download_video: yt-dlp ok (fallback)", extra=extra)
    return result.returncode == 0


def _apply_faststart(output_path: str, extra: dict) -> None:
    """Apply faststart to downloaded file. Best-effort, logs on failure."""
    # output_path may contain %(ext)s — resolve actual file
    import glob as _glob
    base = output_path.replace("%(ext)s", "")
    for ext in ["mp4", "webm", "mkv"]:
        candidate = f"{base}.{ext}"
        if os.path.isfile(candidate) and candidate.endswith(".mp4"):
            if _ensure_faststart(candidate):
                details_logger.info("faststart applied", extra=extra)
            else:
                details_logger.info("faststart skipped (ffmpeg unavailable or failed)", extra=extra)
            break


def download_audio(url: str, output_path: str) -> bool:
    """Extract audio as MP3."""
    ytdlp = _find_ytdlp()
    extra = _log_extra(url)
    logger.info("download_audio: running yt-dlp", extra=extra)
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
    if result.returncode != 0:
        logger.warning("download_audio: yt-dlp failed (code %d)", result.returncode, extra=extra)
    else:
        logger.info("download_audio: yt-dlp ok", extra=extra)
    return result.returncode == 0


def download_images(url: str, output_dir: str) -> list[str]:
    """Download images from carousel/gallery post using gallery-dl.

    Falls back to yt-dlp thumbnail extraction if gallery-dl is unavailable.
    Returns list of file paths.
    """
    # Try gallery-dl first (handles carousels well with cookies)
    from config import IG_COOKIES_PATH
    images = download_gallery_dl_images(url, output_dir, IG_COOKIES_PATH)
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


def download_gallery_dl_images(url: str, output_dir: str, cookies: str = "") -> list[str]:
    """Download images using gallery-dl.

    Requires gallery-dl binary. Cookies needed for Instagram, not for TikTok.
    Returns list of downloaded file paths, or empty list on failure.
    """
    gd_path = _find_gallery_dl()
    if not gd_path:
        return []

    os.makedirs(output_dir, exist_ok=True)
    output_dir = os.path.abspath(output_dir)

    cmd = [gd_path, "-d", output_dir]
    if cookies:
        # Resolve to absolute path so subprocess finds it regardless of cwd
        cookies = os.path.abspath(cookies)
        if not os.path.isfile(cookies):
            return []
        cmd.extend(["--cookies", cookies])
    cmd.append(url)

    extra = _log_extra(url)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        logger.warning("gallery-dl: failed (code %d)", result.returncode, extra=extra)
        return []

    images = sorted(
        glob.glob(f"{output_dir}/**/*.jpg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.jpeg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.png", recursive=True)
        + glob.glob(f"{output_dir}/**/*.webp", recursive=True)
    )
    return images


def download_gallery_dl_video(url: str, output_dir: str) -> str | None:
    """Download video using gallery-dl.

    Args:
        url: The URL to download from.
        output_dir: Directory to download into (gallery-dl creates subdirs).

    Returns:
        Downloaded video file path, or None on failure.
    """
    gd_path = _find_gallery_dl()
    if not gd_path:
        return None

    os.makedirs(output_dir, exist_ok=True)
    output_dir = os.path.abspath(output_dir)

    cmd = [gd_path, "-d", output_dir, url]
    extra = _log_extra(url)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.warning("gallery-dl video: timed out after 60s", extra=extra)
        return None

    if result.returncode != 0:
        logger.warning("gallery-dl video: failed (code %d)", result.returncode, extra=extra)
        return None

    # Find downloaded video files
    video_extensions = ["*.mp4", "*.webm", "*.mkv", "*.mov"]
    videos = []
    for ext in video_extensions:
        videos.extend(glob.glob(f"{output_dir}/**/{ext}", recursive=True))

    if not videos:
        logger.warning("gallery-dl video: no video files found in %s", output_dir, extra=extra)
        return None

    # Return the largest video found
    return max(videos, key=os.path.getsize)
