"""TikTok download logic."""

import os

from config import MAX_FILE_SIZE
from downloader import download_video, download_gallery_dl_images, get_metadata
from telegram_utils import send_images
from utils import cleanup_dir, find_downloaded_file, cleanup_video_files, make_video_tmp_path, make_tmp_dir
from logging_config import details_logger as _log

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


async def handle_tiktok(update, context, url: str) -> bool:
    """Handle TikTok URL: check metadata for photo posts, fallback to gallery-dl.

    Returns True if content was sent successfully, False otherwise.
    """
    reply_params = {"message_id": update.message.message_id}
    base = None

    try:
        # Best-effort: check metadata to detect photo posts early
        metadata = get_metadata(url)
        if metadata:
            ext = (metadata.get("ext") or "").lower()
            if ext in IMAGE_EXTENSIONS:
                _log.info("tiktok: metadata indicates photo post (ext=%s), trying gallery-dl", ext)
                out_dir = make_tmp_dir()
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

        # Try video download
        _, output_path, base = make_video_tmp_path()

        success = download_video(url, output_path, MAX_FILE_SIZE, platform="tiktok")
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

        # Fallback: try gallery-dl for photo posts
        out_dir = make_tmp_dir()
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
            cleanup_video_files(base)
