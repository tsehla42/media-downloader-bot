"""TikTok download logic."""

import logging
import os
import uuid

from config import DOWNLOAD_DIR, MAX_FILE_SIZE
from downloader import download_video, download_gallery_dl_images
from telegram_utils import send_images
from utils import cleanup_file, cleanup_dir

_log = logging.getLogger(__name__)


async def handle_tiktok(update, context, url: str) -> bool:
    """Handle TikTok URL: try video download first, fallback to gallery-dl for photos.

    Returns True if content was sent successfully, False otherwise.
    """
    reply_params = {"message_id": update.message.message_id}
    base = None

    try:
        # Try video download first
        tmp_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
        base = os.path.join(DOWNLOAD_DIR, tmp_id)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        success = download_video(url, output_path, MAX_FILE_SIZE, platform="tiktok")
        if success:
            downloaded = None
            for ext in ["mp4", "webm", "mkv"]:
                candidate = f"{base}.{ext}"
                if os.path.isfile(candidate):
                    downloaded = candidate
                    break

            if downloaded:
                with open(downloaded, "rb") as f:
                    await update.message.reply_video(
                        video=f,
                        reply_parameters=reply_params,
                    )
                context.user_data["_content_type"] = "video"
                try:
                    context.user_data["_file_size_mb"] = round(os.path.getsize(downloaded) / (1024 * 1024), 2)
                except OSError:
                    pass
                context.user_data["_request_success"] = True
                return True

        # Fallback: try gallery-dl for photo posts
        tmp_id = uuid.uuid4().hex[:8]
        out_dir = os.path.join(DOWNLOAD_DIR, tmp_id)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        try:
            images = download_gallery_dl_images(url, out_dir, "")
            if images:
                total_size = await send_images(update.message, images, reply_params)
                context.user_data["_content_type"] = "image"
                context.user_data["_file_size_mb"] = round(total_size / (1024 * 1024), 2) if total_size > 0 else None
                context.user_data["_request_success"] = True
                return True
        finally:
            cleanup_dir(out_dir)

        return False

    finally:
        if base:
            for ext in ["mp4", "webm", "mkv"]:
                cleanup_file(f"{base}.{ext}")
