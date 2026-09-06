"""Instagram download logic."""

import os
import re

from config import IG_COOKIES_PATH, MAX_FILE_SIZE
from downloader import download_video, download_gallery_dl_images
from telegram_utils import send_images
from utils import cleanup_dir, find_downloaded_file, cleanup_video_files, make_video_tmp_path, make_tmp_dir

from logging_config import details_logger as _log


async def handle_instagram(update, context, url: str) -> bool:
    """Handle Instagram URL: try video download first, fallback to images.

    Returns True if content was sent successfully, False otherwise.
    """
    # Stories always require cookies — skip early if cookies file not available
    if re.search(r"/stories/", url) and not os.path.isfile(IG_COOKIES_PATH):
        _log.info("instagram: stories URL without cookies, skipping", extra={"url": url})
        return False

    reply_params = {"message_id": update.message.message_id, "allow_sending_without_reply": True}
    base = None

    try:
        # Try video download first
        _, output_path, base = make_video_tmp_path()

        success = download_video(url, output_path, MAX_FILE_SIZE)
        if success:
            downloaded = find_downloaded_file(base)

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
        out_dir = make_tmp_dir()
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
            cleanup_video_files(base)
