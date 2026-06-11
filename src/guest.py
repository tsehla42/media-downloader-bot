"""Bot API 10.0 Guest Mode handler.

Handles guest_message updates using python-telegram-bot's native Bot API 10.0
support. When a user mentions @botname in any chat, the bot receives a
guest_message update and replies via answerGuestQuery().
"""

import asyncio
import logging
import os
import time
import uuid

import httpx
from telegram import Update
from telegram.ext import ContextTypes

from auth import is_user_allowed, was_notified_guest, mark_notified_guest
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, INSTAGRAM_COOKIES, STORAGE_CHANNEL_ID
from logging_config import (
    details_logger,
    log_guest_request_received,
    log_guest_request_completed,
    log_unauthorized_access,
    set_current_request_id,
)
from platforms import detect_platform, extract_domain
from utils import extract_urls, cleanup_file, cleanup_dir, get_gallery_dl_domains, get_ytdlp_domains
from downloader import (
    get_metadata,
    download_video,
    download_gallery_dl_images,
    download_gallery_dl_video,
)

logger = logging.getLogger("media_downloader.guest")

# Telegram Bot API base URL for file uploads
_API_BASE = "https://api.telegram.org/bot{token}/{method}"


# ---------------------------------------------------------------------------
# InlineQueryResult helpers
# ---------------------------------------------------------------------------

def _text_result(text: str) -> dict:
    """Build InlineQueryResultArticle for text response."""
    return {
        "type": "article",
        "id": uuid.uuid4().hex[:8],
        "title": text[:100],
        "input_message_content": {"message_text": text},
    }


def _video_result(file_id: str, title: str = "Video", thumbnail_url: str = "") -> dict:
    """Build InlineQueryResultVideo for video response.

    Uses raw dict to pass video_file_id directly — ptb's InlineQueryResultVideo
    requires video_url in its constructor but Telegram ignores it when
    video_file_id is present.
    """
    return {
        "type": "video",
        "id": uuid.uuid4().hex[:8],
        "video_file_id": file_id,
        "title": title[:100],
        "mime_type": "video/mp4",
        "thumbnail_url": thumbnail_url or "",
    }


def _photo_result(file_id: str) -> dict:
    """Build InlineQueryResultPhoto for single photo response."""
    return {
        "type": "photo",
        "id": uuid.uuid4().hex[:8],
        "photo_file_id": file_id,
        "thumbnail_url": "",
    }


def _media_group_result(file_ids: list[str]) -> dict:
    """Show first image from a media group (inline results don't support groups)."""
    if file_ids:
        return _photo_result(file_ids[0])
    return _text_result("No images found")


# ---------------------------------------------------------------------------
# Guest message handler (ptb native)
# ---------------------------------------------------------------------------

async def handle_guest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a guest_message update from Bot API 10.0.

    This is a standard ptb handler registered with:
        MessageHandler(filters.UpdateType.GUEST_MESSAGE, handle_guest)
    """
    guest_msg = update.guest_message
    if not guest_msg:
        return

    # Caller info is in the standard 'from' field (mapped to from_user by ptb)
    caller = guest_msg.from_user
    caller_id = caller.id if caller else 0
    guest_query_id = guest_msg.guest_query_id
    text = guest_msg.text or ""
    chat = guest_msg.chat

    request_id = uuid.uuid4().hex[:8]
    set_current_request_id(request_id)

    # Auth check
    if not is_user_allowed(caller_id):
        if not was_notified_guest(caller_id):
            await context.bot.answer_guest_query(
                guest_query_id,
                result=_text_result("You are not authorized to use this bot"),
            )
            mark_notified_guest(caller_id)
        log_unauthorized_access(caller, chat, "guest")
        return

    # Extract URLs from tag message text
    urls = extract_urls(text)

    # Check replied-to message for URLs
    reply_data = None
    if guest_msg.reply_to_message:
        replied_to = guest_msg.reply_to_message
        replied_text = replied_to.text or ""
        urls = extract_urls(replied_text) if not urls else urls
        replied_user = getattr(replied_to, "from_user", None)

        # Determine message content: text or media type
        message_content = replied_text[:200] if replied_text else None
        if not message_content:
            if getattr(replied_to, "photo", None):
                message_content = "[photo]"
            elif getattr(replied_to, "video", None):
                message_content = "[video]"
            elif getattr(replied_to, "animation", None):
                message_content = "[animation]"
            elif getattr(replied_to, "document", None):
                message_content = "[document]"
            elif getattr(replied_to, "sticker", None):
                message_content = "[sticker]"

        reply_data = {
            "user_id": replied_user.id if replied_user else None,
            "name": getattr(replied_user, "first_name", None) if replied_user else None,
            "username": getattr(replied_user, "username", None) if replied_user else None,
            "message": message_content,
        }

    if not urls:
        # Silent ignore when replying to bot message without URL
        if not guest_msg.reply_to_message:
            await context.bot.answer_guest_query(
                guest_query_id,
                result=_text_result("Please include a URL to download"),
            )
        return

    # Log Guest request received (only when URL is present)
    log_guest_request_received(
        request_id=request_id,
        guest_query_id=guest_query_id,
        url=text,
        caller=caller,
        chat=chat,
        reply=reply_data,
    )

    # Process first URL
    url = urls[0]
    platform = None
    try:
        platform = detect_platform(url)
    except Exception as e:
        logger.error("Platform detection failed: %s", e)

    # For gallery-dl URLs, use domain as platform name (matches P2P handler logging)
    if not platform:
        platform = extract_domain(url)

    start_time = time.time()

    try:
        result = await _download_and_build_result(url, platform)
        await context.bot.answer_guest_query(guest_query_id, result=result)

        duration_ms = int((time.time() - start_time) * 1000)
        log_guest_request_completed(
            request_id=request_id,
            guest_query_id=guest_query_id,
            url=url,
            platform=platform,
            duration_ms=duration_ms,
            success=True,
            caller=caller,
            chat=chat,
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        log_guest_request_completed(
            request_id=request_id,
            guest_query_id=guest_query_id,
            url=url,
            platform=platform,
            duration_ms=duration_ms,
            success=False,
            error=str(e),
            caller=caller,
            chat=chat,
        )
        await context.bot.answer_guest_query(
            guest_query_id,
            result=_text_result(f"Download failed: {e}"),
        )


# ---------------------------------------------------------------------------
# Download pipeline
# ---------------------------------------------------------------------------

async def _download_and_build_result(url: str, platform: str | None) -> dict:
    """Download media and return InlineQueryResult."""
    try:
        # Check if it's a main platform (yt/tt/ig)
        if platform == "youtube":
            return await _download_youtube(url)

        if platform == "tiktok":
            return await _download_media_result(url, "tiktok")

        if platform == "instagram":
            return await _download_media_result(url, "instagram")

        # Check yt-dlp domains
        domain = extract_domain(url)
        ytdlp_domains = get_ytdlp_domains()
        if domain in ytdlp_domains:
            # Generic yt-dlp download
            return await _ytdlp_generic_result(url)

        # Check gallery-dl domains
        gallery_dl_domains = get_gallery_dl_domains()
        if domain in gallery_dl_domains:
            return await _gallery_dl_result(url)

        # Unsupported
        return _text_result("Unsupported platform")

    except Exception as e:
        return _text_result(f"Error: {e}")


async def _download_youtube(url: str) -> dict:
    """Download YouTube video and return InlineQueryResult."""
    metadata = await asyncio.to_thread(get_metadata, url)
    if not metadata:
        return _text_result("Could not fetch video metadata")

    title = metadata.get("title", "video")
    estimated_size = metadata.get("filesize") or metadata.get("filesize_approx")
    if estimated_size and estimated_size > MAX_FILE_SIZE * 1024 * 1024:
        return _text_result("This video is above Telegram's 50MB limit")

    thumbnail_url = metadata.get("thumbnail", "")
    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        success = await asyncio.to_thread(download_video, url, output_path)
        if not success:
            return _text_result("Download failed")

        for ext in ["mp4", "webm", "mkv"]:
            filepath = f"{base}.{ext}"
            if os.path.isfile(filepath):
                file_id = await _upload_to_telegram(filepath, "video")
                if file_id:
                    return _video_result(file_id, title=title, thumbnail_url=thumbnail_url)
                return _text_result("Failed to upload video to Telegram")
        return _text_result("Downloaded file not found")
    finally:
        for ext in ["mp4", "webm", "mkv"]:
            fpath = f"{base}.{ext}"
            if os.path.isfile(fpath):
                os.unlink(fpath)


async def _download_media_result(url: str, platform: str) -> dict:
    """Download TikTok/Instagram content."""
    output_dir = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Try video download first
        video_path = os.path.join(output_dir, f"{platform}.mp4")
        success = await asyncio.to_thread(download_video, url, video_path)
        if success:
            file_id = await _upload_to_telegram(video_path, "video")
            if file_id:
                return _video_result(file_id, title=f"{platform.title()} video")

        # Try image/gallery-dl fallback
        cookies = INSTAGRAM_COOKIES if platform == "instagram" else ""
        images = await asyncio.to_thread(download_gallery_dl_images, url, output_dir, cookies)
        if images:
            file_ids = []
            for img_path in images[:10]:
                fid = await _upload_to_telegram(img_path, "photo")
                if fid:
                    file_ids.append(fid)
            if file_ids:
                if len(file_ids) == 1:
                    return _photo_result(file_ids[0])
                return _media_group_result(file_ids)

        # Try gallery-dl video fallback
        video = await asyncio.to_thread(download_gallery_dl_video, url, output_dir)
        if video:
            file_id = await _upload_to_telegram(video, "video")
            if file_id:
                return _video_result(file_id, title=f"{platform.title()} video")

        return _text_result("Could not download media from this URL")
    finally:
        cleanup_dir(output_dir)


async def _ytdlp_generic_result(url: str) -> dict:
    """Generic yt-dlp download for non-yt/tt/ig sites."""
    metadata = await asyncio.to_thread(get_metadata, url)
    if not metadata:
        return _text_result("Failed to fetch metadata")

    title = metadata.get("title", "video")
    estimated_size = metadata.get("filesize") or metadata.get("filesize_approx")
    if estimated_size and estimated_size > MAX_FILE_SIZE * 1024 * 1024:
        return _text_result("This video is above Telegram's 50MB limit")

    thumbnail_url = metadata.get("thumbnail", "")
    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        success = await asyncio.to_thread(download_video, url, output_path)
        if not success:
            return _text_result("Download failed")

        for ext in ["mp4", "webm", "mkv"]:
            filepath = f"{base}.{ext}"
            if os.path.isfile(filepath):
                file_id = await _upload_to_telegram(filepath, "video")
                if file_id:
                    return _video_result(file_id, title=title, thumbnail_url=thumbnail_url)
                return _text_result("Failed to upload video to Telegram")
        return _text_result("Downloaded file not found")
    finally:
        for ext in ["mp4", "webm", "mkv"]:
            fpath = f"{base}.{ext}"
            if os.path.isfile(fpath):
                os.unlink(fpath)


async def _gallery_dl_result(url: str) -> dict:
    """gallery-dl fallback for unsupported platforms."""
    output_dir = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        images = await asyncio.to_thread(download_gallery_dl_images, url, output_dir, "")
        if images:
            file_ids = []
            for img_path in images[:10]:
                fid = await _upload_to_telegram(img_path, "photo")
                if fid:
                    file_ids.append(fid)
            if file_ids:
                if len(file_ids) == 1:
                    return _photo_result(file_ids[0])
                return _media_group_result(file_ids)

        video = await asyncio.to_thread(download_gallery_dl_video, url, output_dir)
        if video:
            file_id = await _upload_to_telegram(video, "video")
            if file_id:
                return _video_result(file_id, title="Video")

        return _text_result("Unsupported platform or content not found")
    finally:
        cleanup_dir(output_dir)


# ---------------------------------------------------------------------------
# File upload to storage channel
# ---------------------------------------------------------------------------

async def _upload_to_telegram(file_path: str, media_type: str) -> str | None:
    """Upload a local file to the storage channel and return the file_id."""
    if not STORAGE_CHANNEL_ID:
        details_logger.warning(
            "upload_to_telegram skipped — STORAGE_CHANNEL_ID not configured",
            extra={"extra_data": {"file_path": file_path}},
        )
        return None

    from config import BOT_TOKEN
    url = _API_BASE.format(token=BOT_TOKEN, method=f"send{media_type.capitalize()}")

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            with open(file_path, "rb") as f:
                if media_type == "video":
                    files = {"video": f}
                elif media_type == "photo":
                    files = {"photo": f}
                else:
                    files = {"document": f}
                data = {"chat_id": STORAGE_CHANNEL_ID}

                response = await client.post(url, data=data, files=files)
                result = response.json()

                if not result.get("ok"):
                    details_logger.warning(
                        "upload_to_telegram failed",
                        extra={"extra_data": {"error": result.get("description"), "file_path": file_path}},
                    )
                    return None

                msg = result.get("result", {})
                if media_type == "video":
                    return msg.get("video", {}).get("file_id")
                elif media_type == "photo":
                    # Telegram returns photo as list of PhotoSize (smallest→largest)
                    photo = msg.get("photo", [])
                    if isinstance(photo, list) and photo:
                        return photo[-1].get("file_id")
                    return photo.get("file_id") if isinstance(photo, dict) else None
                else:
                    return msg.get("document", {}).get("file_id")

    except Exception:
        details_logger.exception(
            "upload_to_telegram exception",
            extra={"extra_data": {"file_path": file_path, "media_type": media_type}},
        )
        return None
