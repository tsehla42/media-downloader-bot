import glob
import json
import os
import subprocess
import shutil
import sys

from logging_config import details_logger as logger, get_current_request_id
from messages import MSG_FETCH_FAILED

MAX_FILE_SIZE_MB = 50

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
TIKTOK_REFERER = "https://www.tiktok.com/"

# Format selector matching download_video() — used by get_metadata() for
# accurate pre-download size estimates (avoids rejecting videos whose
# bestvideo+bestaudio streams exceed 50 MB but whose MP4 fallback fits).
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
VIDEO_FORMAT_SELECTOR = (
    f"best[ext=mp4][filesize<{MAX_FILE_SIZE_BYTES}]"
    f"/best[ext=mp4]"
    f"/best[filesize<{MAX_FILE_SIZE_BYTES}]"
    f"/best"
)


class DownloadAuthRequired(Exception):
    """Raised when content requires platform login/cookies to access."""


class DownloadError(Exception):
    """Download failed with a user-facing message and raw technical details.

    Attributes:
        user_message: Safe message to show to the user (MSG_* constant).
        raw_error: Technical error details for logging (never shown to users).
    """
    def __init__(self, user_message: str, raw_error: str | None = None):
        self.user_message = user_message
        self.raw_error = raw_error
        super().__init__(user_message)


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


def get_metadata(url: str, format_selector: str | None = None, referer: str = "") -> dict | None:
    """Get video metadata via yt-dlp --dump-json.

    Args:
        format_selector: Optional yt-dlp -f flag. When set, metadata reflects
            the size of the format that will actually be downloaded (important
            for YouTube where download_video() forces MP4, not bestvideo).
        referer: Optional Referer header (e.g. for TikTok anti-bot bypass).
    """
    ytdlp = _find_ytdlp()
    try:
        cmd = [ytdlp, "--dump-json", "--no-download", "--no-playlist", "--user-agent", USER_AGENT]
        if referer:
            cmd.extend(["--referer", referer])
        if format_selector:
            cmd.extend(["-f", format_selector])
        cmd.append(url)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "Sign in to confirm your age" in stderr:
                raise DownloadAuthRequired(stderr)
            extra = _log_extra(url)
            extra["yt_dlp_stderr"] = stderr
            logger.warning("get_metadata: yt-dlp failed (code %d)", result.returncode, extra=extra)
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        extra = _log_extra(url)
        logger.warning("get_metadata: timed out after 60s", extra=extra)
        return None
    except json.JSONDecodeError:
        extra = _log_extra(url)
        logger.warning("get_metadata: invalid JSON output", extra=extra)
        return None
    except FileNotFoundError:
        return None


def _ensure_faststart(filepath: str) -> str | None:
    """Ensure video file is MP4 with moov atom at front for Telegram streaming.

    For .mp4 files: moves moov atom to front (faststart) without re-encoding.
    For non-MP4 files (webm, mkv, mov): remuxes to .mp4 with faststart.
    Returns the path to the streamable file, or None on failure.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return filepath  # ffmpeg not available, return original

    is_mp4 = filepath.endswith(".mp4")
    tmp = filepath + ".faststart.mp4"

    try:
        if is_mp4:
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
        else:
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-i", filepath,
                    "-c", "copy", "-movflags", "+faststart",
                    "-f", "mp4",
                    tmp,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

        if result.returncode == 0 and os.path.isfile(tmp):
            if not is_mp4:
                new_path = os.path.splitext(filepath)[0] + ".mp4"
                os.replace(tmp, new_path)
                return new_path
            else:
                os.replace(tmp, filepath)
                return filepath
        if os.path.isfile(tmp):
            os.unlink(tmp)
    except (subprocess.TimeoutExpired, OSError):
        if os.path.isfile(tmp):
            os.unlink(tmp)
    return None


def download_video(url: str, output_path: str, max_size_mb: int = MAX_FILE_SIZE_MB, platform: str = "") -> bool:
    """Download video, retrying with lower quality if too large."""
    ytdlp = _find_ytdlp()
    max_bytes = max_size_mb * 1024 * 1024
    extra = _log_extra(url, platform)

    extra_args = []
    if platform == "tiktok":
        extra_args.extend(["--extractor-args", "tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com"])
        extra_args.extend(["--referer", TIKTOK_REFERER])

    logger.info("download_video: running yt-dlp", extra=extra)
    result = subprocess.run(
        [
            ytdlp,
            "-f", f"best[ext=mp4][filesize<{max_bytes}]/best[ext=mp4]/best[filesize<{max_bytes}]/best",
            "--merge-output-format", "mp4",
            "-o", output_path,
            "--no-playlist",
            "--user-agent", USER_AGENT,
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
            "-f", f"worst[ext=mp4][filesize<{max_bytes}]/worst[ext=mp4]/worst[filesize<{max_bytes}]/worst",
            "--merge-output-format", "mp4",
            "-o", output_path,
            "--no-playlist",
            "--user-agent", USER_AGENT,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        extra["yt_dlp_stderr"] = stderr
        if ("Log in for access" in stderr
            or "This content isn't available to everyone" in stderr
            or "Sign in to confirm your age" in stderr):
            raise DownloadAuthRequired(stderr)
        logger.warning("download_video: yt-dlp failed (code %d)", result.returncode, extra=extra)
    else:
        _apply_faststart(output_path, extra)
        logger.info("download_video: yt-dlp ok (fallback)", extra=extra)
    return result.returncode == 0


def _apply_faststart(output_path: str, extra: dict) -> None:
    """Apply faststart to downloaded file. Best-effort, logs on failure.

    For MP4 files: moves moov atom to front.
    For non-MP4 (webm, mkv): remuxes to MP4 with faststart.
    """
    base = output_path.replace("%(ext)s", "")
    for ext in ["mp4", "webm", "mkv"]:
        candidate = f"{base}.{ext}"
        if os.path.isfile(candidate):
            result = _ensure_faststart(candidate)
            if result:
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
            "--user-agent", USER_AGENT,
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        extra["yt_dlp_stderr"] = stderr
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
            "--user-agent", USER_AGENT,
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
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        logger.warning("gallery-dl images: timed out after 60s", extra=extra)
        raise DownloadError(
            MSG_FETCH_FAILED,
            raw_error=str(e),
        ) from e

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        extra["gallery_dl_stderr"] = stderr
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
    except subprocess.TimeoutExpired as e:
        logger.warning("gallery-dl video: timed out after 60s", extra=extra)
        raise DownloadError(
            MSG_FETCH_FAILED,
            raw_error=str(e),
        ) from e

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        extra["gallery_dl_stderr"] = stderr
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

    # Return the largest video found, apply faststart
    video_path = max(videos, key=os.path.getsize)
    return _ensure_faststart(video_path)
