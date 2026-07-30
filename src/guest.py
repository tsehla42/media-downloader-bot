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
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, IG_COOKIES_PATH, STORAGE_CHANNEL_ID
from logging_config import (
    details_logger,
    error_logger,
    log_guest_request_received,
    log_guest_request_completed,
    log_unauthorized_access,
    set_current_request_id,
    _build_forwarded_dict,
)
from platforms import detect_platform, extract_domain
from utils import extract_urls, cleanup_file, cleanup_dir, get_gallery_dl_domains, get_ytdlp_domains
from cache import get_cached, store
from downloader import (
    get_metadata,
    download_video,
    download_gallery_dl_images,
    download_gallery_dl_video,
    DownloadAuthRequired,
    DownloadError,
)
from messages import (
    MSG_UNAUTHORIZED, MSG_NO_URL, MSG_LOGIN_REQUIRED, MSG_SIZE_LIMIT,
    MSG_UNSUPPORTED_PLATFORM, MSG_METADATA_FAILED, MSG_DOWNLOAD_FAILED,
    MSG_GUEST_DOWNLOAD_FAILED, MSG_GUEST_NO_IMAGES,
    MSG_GUEST_METADATA_FAILED, MSG_GUEST_UPLOAD_FAILED,
    MSG_GUEST_DOWNLOAD_NOT_FOUND, MSG_GUEST_COULD_NOT_DOWNLOAD,
    MSG_GUEST_CONTENT_NOT_FOUND,
)

logger = logging.getLogger("media_downloader.guest")

# Media type labels for logging replied-to message content
MEDIA_TYPES = {
    "photo": "[photo]",
    "video": "[video]",
    "animation": "[animation]",
    "document": "[document]",
    "sticker": "[sticker]",
}

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
    return _text_result(MSG_GUEST_NO_IMAGES)


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
    forwarded = _build_forwarded_dict(guest_msg)

    request_id = uuid.uuid4().hex[:8]
    set_current_request_id(request_id)

    # Extract URLs from tag message text
    urls = extract_urls(text)

    # Check replied-to message for URLs
    reply_data = None
    if guest_msg.reply_to_message:
        replied_to = guest_msg.reply_to_message
        replied_user = getattr(replied_to, "from_user", None)
        # Don't extract URLs from bot's own messages (error messages contain help links)
        if not (replied_user and replied_user.is_bot):
            replied_text = replied_to.text or ""
            urls = extract_urls(replied_text) if not urls else urls

        # Determine message content: text or media type
        replied_text = replied_to.text or ""
        message_content = replied_text[:200] if replied_text else None
        if not message_content:
            message_content = next(
                (label for attr, label in MEDIA_TYPES.items() if getattr(replied_to, attr, None)),
                None,
            )

        reply_data = {
            "user_id": replied_user.id if replied_user else None,
            "name": getattr(replied_user, "first_name", None) if replied_user else None,
            "username": getattr(replied_user, "username", None) if replied_user else None,
            "message": message_content,
        }

    if not urls:
        # Silent ignore when replying to bot message without URL
        if not guest_msg.reply_to_message:
            # Only show hint to authorized users; unauthorized get silently ignored
            if is_user_allowed(caller_id):
                await context.bot.answer_guest_query(
                    guest_query_id,
                    result=_text_result(MSG_NO_URL),
                )
        return

    # Auth check — only when user is trying to download (URL present)
    if not is_user_allowed(caller_id):
        if not was_notified_guest(caller_id):
            await context.bot.answer_guest_query(
                guest_query_id,
                result=_text_result(MSG_UNAUTHORIZED),
            )
            mark_notified_guest(caller_id)
        log_unauthorized_access(caller, chat, "guest")
        return

    # Fetch chat owner info for private chats (to show both participants)
    chat_owner_name = None
    chat_owner_username = None
    if getattr(chat, "type", None) == "private":
        try:
            member = await context.bot.get_chat_member(chat.id, chat.id)
            user_obj = getattr(member, "user", None)
            if user_obj:
                chat_owner_name = getattr(user_obj, "first_name", None)
                chat_owner_username = getattr(user_obj, "username", None)
        except Exception:
            pass  # Fallback: show only caller info

    # Log Guest request received (only when URL is present)
    log_guest_request_received(
        request_id=request_id,
        guest_query_id=guest_query_id,
        url=text,
        caller=caller,
        chat=chat,
        reply=reply_data,
        chat_owner_name=chat_owner_name,
        chat_owner_username=chat_owner_username,
        forwarded=forwarded,
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
        result, content_type, file_size_mb, cache_hit = await _download_and_build_result(url, platform)
        await context.bot.answer_guest_query(guest_query_id, result=result)

        duration_ms = int((time.time() - start_time) * 1000)
        log_guest_request_completed(
            request_id=request_id,
            guest_query_id=guest_query_id,
            url=url,
            platform=platform,
            duration_ms=duration_ms,
            success=True,
            content_type=content_type,
            file_size_mb=file_size_mb,
            cache_hit=cache_hit,
            caller=caller,
            chat=chat,
            chat_owner_name=chat_owner_name,
            chat_owner_username=chat_owner_username,
            forwarded=forwarded,
        )
    except DownloadError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        details_logger.warning("guest: download error: %s", e.raw_error, extra={"request_id": request_id, "url": url})
        log_guest_request_completed(
            request_id=request_id,
            guest_query_id=guest_query_id,
            url=url,
            platform=platform,
            duration_ms=duration_ms,
            success=False,
            error=e.user_message,
            caller=caller,
            chat=chat,
            chat_owner_name=chat_owner_name,
            chat_owner_username=chat_owner_username,
            forwarded=forwarded,
        )
        await context.bot.answer_guest_query(
            guest_query_id,
            result=_text_result(e.user_message),
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
            chat_owner_name=chat_owner_name,
            chat_owner_username=chat_owner_username,
            forwarded=forwarded,
        )
        await context.bot.answer_guest_query(
            guest_query_id,
            result=_text_result(MSG_DOWNLOAD_FAILED),
        )


# ---------------------------------------------------------------------------
# Download pipeline
# ---------------------------------------------------------------------------

async def _download_and_build_result(url: str, platform: str | None) -> tuple[dict, str | None, float | None, bool]:
    """Download media and return (InlineQueryResult, content_type, file_size_mb, cache_hit).

    Checks cache first. On miss, downloads and caches the result.
    Raises ValueError when all download methods fail (expected failure).
    Other exceptions propagate as unexpected errors.
    """
    # Check cache first
    metadata = None
    if platform == "tiktok":
        # Fetch metadata to get video ID for short URLs
        metadata = await asyncio.to_thread(get_metadata, url)
    cached = get_cached(url, platform, metadata)
    if cached:
        file_id, media_type = cached
        if media_type == "video":
            return _video_result(file_id, title="Cached video"), "video", None, True
        elif media_type in ("photo", "image"):
            return _photo_result(file_id), "image", None, True

    # Cache miss - proceed with download
    metadata = None
    if platform == "youtube":
        result, content_type, file_size_mb = await _download_youtube(url)
    elif platform == "tiktok":
        # Fetch metadata first to get video ID for short URLs
        metadata = await asyncio.to_thread(get_metadata, url)
        result, content_type, file_size_mb = await _download_media_result(url, "tiktok")
    elif platform == "instagram":
        result, content_type, file_size_mb = await _download_media_result(url, "instagram")
    else:
        domain = extract_domain(url)
        ytdlp_domains = get_ytdlp_domains()
        if domain in ytdlp_domains:
            result, content_type, file_size_mb = await _ytdlp_generic_result(url)
        else:
            gallery_dl_domains = get_gallery_dl_domains()
            if domain in gallery_dl_domains:
                result, content_type, file_size_mb = await _gallery_dl_result(url)
            else:
                return _text_result(MSG_UNSUPPORTED_PLATFORM), None, None, False

    # Cache successful result
    if result and result.get("video_file_id"):
        store(url, platform, result["video_file_id"], "video",
              result.get("title", ""), file_size_mb or 0.0, metadata)
    elif result and result.get("photo_file_id"):
        store(url, platform, result["photo_file_id"], "photo",
              result.get("title", ""), file_size_mb or 0.0, metadata)

    return result, content_type, file_size_mb, False


async def _download_youtube(url: str) -> tuple[dict, str, float | None]:
    """Download YouTube video and return (InlineQueryResult, content_type, file_size_mb)."""
    try:
        metadata = await asyncio.to_thread(get_metadata, url)
    except DownloadAuthRequired:
        return _text_result(MSG_LOGIN_REQUIRED), "video", None
    if not metadata:
        return _text_result(MSG_GUEST_METADATA_FAILED), "video", None

    title = metadata.get("title", "video")
    estimated_size = metadata.get("filesize") or metadata.get("filesize_approx")
    if estimated_size and estimated_size > MAX_FILE_SIZE * 1024 * 1024:
        return _text_result(MSG_SIZE_LIMIT), "video", None

    thumbnail_url = metadata.get("thumbnail", "")
    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        success = await asyncio.to_thread(download_video, url, output_path)
        if not success:
            raise ValueError(MSG_DOWNLOAD_FAILED)

        for ext in ["mp4", "webm", "mkv"]:
            filepath = f"{base}.{ext}"
            if os.path.isfile(filepath):
                file_size = os.path.getsize(filepath)
                file_size_mb = round(file_size / (1024 * 1024), 2)
                file_id = await _upload_to_telegram(filepath, "video")
                if file_id:
                    return _video_result(file_id, title=title, thumbnail_url=thumbnail_url), "video", file_size_mb
                raise ValueError(MSG_GUEST_UPLOAD_FAILED)
        raise ValueError(MSG_GUEST_DOWNLOAD_NOT_FOUND)
    finally:
        for ext in ["mp4", "webm", "mkv"]:
            fpath = f"{base}.{ext}"
            if os.path.isfile(fpath):
                os.unlink(fpath)


async def _download_media_result(url: str, platform: str) -> tuple[dict, str, float | None]:
    """Download TikTok/Instagram content. Returns (result, content_type, file_size_mb)."""
    output_dir = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Try video download first
        video_path = os.path.join(output_dir, f"{platform}.mp4")
        try:
            success = await asyncio.to_thread(download_video, url, video_path)
        except DownloadAuthRequired:
            return _text_result(MSG_LOGIN_REQUIRED), None, None
        if success:
            file_size = os.path.getsize(video_path)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            file_id = await _upload_to_telegram(video_path, "video")
            if file_id:
                return _video_result(file_id, title=f"{platform.title()} video"), "video", file_size_mb
            raise ValueError(MSG_GUEST_UPLOAD_FAILED)

        # Try image/gallery-dl fallback
        cookies = IG_COOKIES_PATH if platform == "instagram" else ""
        images = await asyncio.to_thread(download_gallery_dl_images, url, output_dir, cookies)
        if images:
            file_ids = []
            total_size = 0
            for img_path in images[:10]:
                total_size += os.path.getsize(img_path)
                fid = await _upload_to_telegram(img_path, "photo")
                if fid:
                    file_ids.append(fid)
            if file_ids:
                file_size_mb = round(total_size / (1024 * 1024), 2)
                if len(file_ids) == 1:
                    return _photo_result(file_ids[0]), "image", file_size_mb
                return _media_group_result(file_ids), "image", file_size_mb

        # Try gallery-dl video fallback
        video = await asyncio.to_thread(download_gallery_dl_video, url, output_dir)
        if video:
            file_size = os.path.getsize(video)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            file_id = await _upload_to_telegram(video, "video")
            if file_id:
                return _video_result(file_id, title=f"{platform.title()} video"), "video", file_size_mb

        raise ValueError(MSG_GUEST_COULD_NOT_DOWNLOAD)
    finally:
        cleanup_dir(output_dir)


async def _ytdlp_generic_result(url: str) -> tuple[dict, str, float | None]:
    """Generic yt-dlp download for non-yt/tt/ig sites. Returns (result, content_type, file_size_mb)."""
    try:
        metadata = await asyncio.to_thread(get_metadata, url)
    except DownloadAuthRequired:
        return _text_result(MSG_LOGIN_REQUIRED), "video", None
    if not metadata:
        return _text_result(MSG_METADATA_FAILED), "video", None

    title = metadata.get("title", "video")
    estimated_size = metadata.get("filesize") or metadata.get("filesize_approx")
    if estimated_size and estimated_size > MAX_FILE_SIZE * 1024 * 1024:
        return _text_result(MSG_SIZE_LIMIT), "video", None

    thumbnail_url = metadata.get("thumbnail", "")
    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        success = await asyncio.to_thread(download_video, url, output_path)
        if not success:
            raise ValueError(MSG_DOWNLOAD_FAILED)

        for ext in ["mp4", "webm", "mkv"]:
            filepath = f"{base}.{ext}"
            if os.path.isfile(filepath):
                file_size = os.path.getsize(filepath)
                file_size_mb = round(file_size / (1024 * 1024), 2)
                file_id = await _upload_to_telegram(filepath, "video")
                if file_id:
                    return _video_result(file_id, title=title, thumbnail_url=thumbnail_url), "video", file_size_mb
                raise ValueError(MSG_GUEST_UPLOAD_FAILED)
        raise ValueError(MSG_GUEST_DOWNLOAD_NOT_FOUND)
    finally:
        for ext in ["mp4", "webm", "mkv"]:
            fpath = f"{base}.{ext}"
            if os.path.isfile(fpath):
                os.unlink(fpath)


async def _gallery_dl_result(url: str) -> tuple[dict, str, float | None]:
    """gallery-dl fallback. Returns (result, content_type, file_size_mb)."""
    output_dir = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        images = await asyncio.to_thread(download_gallery_dl_images, url, output_dir, "")
        if images:
            file_ids = []
            total_size = 0
            for img_path in images[:10]:
                total_size += os.path.getsize(img_path)
                fid = await _upload_to_telegram(img_path, "photo")
                if fid:
                    file_ids.append(fid)
            if file_ids:
                file_size_mb = round(total_size / (1024 * 1024), 2)
                if len(file_ids) == 1:
                    return _photo_result(file_ids[0]), "image", file_size_mb
                return _media_group_result(file_ids), "image", file_size_mb

        video = await asyncio.to_thread(download_gallery_dl_video, url, output_dir)
        if video:
            file_size = os.path.getsize(video)
            file_size_mb = round(file_size / (1024 * 1024), 2)
            file_id = await _upload_to_telegram(video, "video")
            if file_id:
                return _video_result(file_id, title="Video"), "video", file_size_mb

        raise ValueError(MSG_GUEST_CONTENT_NOT_FOUND)
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
                if media_type == "video":
                    data["supports_streaming"] = "true"

                response = await client.post(url, data=data, files=files)
                result = response.json()

                if not result.get("ok"):
                    error_logger.error(
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
        error_logger.exception(
            "upload_to_telegram exception",
            extra={"extra_data": {"file_path": file_path, "media_type": media_type}},
        )
        return None
