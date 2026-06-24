"""Instagram download logic."""

import os
import uuid

from config import DOWNLOAD_DIR, IG_COOKIES_PATH, MAX_FILE_SIZE
from downloader import download_video, download_gallery_dl_images
from telegram_utils import send_images
from utils import cleanup_file, cleanup_dir

from logging_config import details_logger as _log


async def handle_instagram(update, context, url: str) -> bool:
    """Handle Instagram URL: try video download first, fallback to images.

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

        success = download_video(url, output_path, MAX_FILE_SIZE)
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
                        supports_streaming=True,
                    )
                context.user_data["_content_type"] = "video"
                try:
                    context.user_data["_file_size_mb"] = round(os.path.getsize(downloaded) / (1024 * 1024), 2)
                except OSError:
                    pass
                context.user_data["_request_success"] = True
                return True

        # Fallback: try images with gallery-dl
        tmp_id = uuid.uuid4().hex[:8]
        out_dir = os.path.join(DOWNLOAD_DIR, tmp_id)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        try:
            _log.info("instagram: trying gallery-dl fallback, cookies=%s", IG_COOKIES_PATH)
            images = download_gallery_dl_images(url, out_dir, IG_COOKIES_PATH)
            _log.info("instagram: gallery-dl returned %d images", len(images))
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
