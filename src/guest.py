"""Bot API 10.0 Guest Mode — unified polling loop.

Telegram Bot API 10.0 (May 2026) introduced Guest Mode, allowing bots to be
invoked via @botname in any chat (even chats the bot isn't a member of). The
bot receives ``guest_message`` updates instead of regular ``message`` updates
when invoked as a guest, and replies via ``answerGuestQuery()``.

This module implements a custom polling loop that takes over from
``app.run_polling()``. Telegram only allows one ``getUpdates`` session per
bot token, so this poller must be the sole consumer. Regular updates are
forwarded to python-telegram-bot's ``Application.process_update()``; guest
updates are handled here.

This module can be replaced when python-telegram-bot adds native Guest Mode
support (tracked upstream).
"""

import asyncio
import json
import logging
import os
import uuid

import httpx
from telegram import Update

from auth import is_user_allowed
from config import GUEST_MODE_ENABLED, DOWNLOAD_DIR, MAX_FILE_SIZE, INSTAGRAM_COOKIES, STORAGE_CHANNEL_ID
from logging_config import details_logger
from platforms import detect_platform
from downloader import (
    get_metadata,
    download_video,
    download_gallery_dl_images,
    download_gallery_dl_video,
)
from utils import extract_urls, cleanup_file, cleanup_dir

logger = logging.getLogger("media_downloader.guest")

# Telegram long-polling timeout in seconds (max allowed by API)
_LONG_POLL_TIMEOUT = 30

# Base URL for Telegram Bot API
_API_BASE = "https://api.telegram.org/bot{token}/{method}"


# ---------------------------------------------------------------------------
# InlineQueryResult helpers
# ---------------------------------------------------------------------------

def _text_result(text: str) -> dict:
    """Build an InlineQueryResultArticle with plain-text message content."""
    return {
        "type": "article",
        "id": uuid.uuid4().hex[:8],
        "title": text[:64],
        "input_message_content": {
            "message_text": text,
        },
    }


def _video_result(file_id: str, title: str = "Video", thumbnail_url: str = "") -> dict:
    """Build an InlineQueryResultVideo with a Telegram file_id."""
    result = {
        "type": "video",
        "id": uuid.uuid4().hex[:8],
        "video_file_id": file_id,
        "title": title,
    }
    if thumbnail_url:
        result["thumb_url"] = thumbnail_url
    return result


def _photo_result(file_id: str) -> dict:
    """Build an InlineQueryResultPhoto with a Telegram file_id."""
    return {
        "type": "photo",
        "id": uuid.uuid4().hex[:8],
        "photo_file_id": file_id,
    }


def _media_group_result(file_ids: list[str]) -> dict:
    """Show first image from a media group (inline results don't support groups)."""
    if file_ids:
        return _photo_result(file_ids[0])
    return _text_result("No images found")


class GuestModePoller:
    """Unified polling loop that handles both regular and guest updates.

    Telegram only permits one ``getUpdates`` session per bot token, so this
    poller replaces ``app.run_polling()``. Regular updates are dispatched to
    the python-telegram-bot ``Application``; guest updates are routed to
    ``_handle_guest_message()``.

    Args:
        bot_token: Telegram bot token string.
        application: python-telegram-bot ``Application`` instance (must be
            initialized but not yet running its own polling loop).
    """

    def __init__(self, bot_token: str, application: "Application") -> None:
        self.bot_token = bot_token
        self.app = application
        self._offset: int = 0
        self._task: asyncio.Task | None = None
        self._running = False
        self._client: httpx.AsyncClient | None = None

    def start(self) -> None:
        """Launch the polling loop as an asyncio task.

        Checks ``GUEST_MODE_ENABLED`` before starting. If disabled, does
        nothing (the caller should fall back to ``app.run_polling()``).
        """
        if not GUEST_MODE_ENABLED:
            logger.info("Guest mode disabled via GUEST_MODE_ENABLED config")
            return

        if self._running:
            logger.warning("GuestModePoller already running")
            return

        self._client = httpx.AsyncClient(timeout=_LONG_POLL_TIMEOUT + 10)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("GuestModePoller started")

    def stop(self) -> None:
        """Stop the polling loop."""
        if not self._running:
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        if self._client:
            asyncio.create_task(self._client.aclose())
            self._client = None
        logger.info("GuestModePoller stopped")

    async def _poll_loop(self) -> None:
        """Long-poll Telegram for updates and route them.

        Regular updates (message, callback_query, my_chat_member) are
        forwarded to ``Application.process_update()``. Guest updates
        (guest_message) go to ``_handle_guest_message()``.

        On error, logs the exception and sleeps 5 seconds before retrying.
        """
        url = _API_BASE.format(token=self.bot_token, method="getUpdates")

        while self._running:
            try:
                params = {
                    "offset": self._offset,
                    "limit": 100,
                    "timeout": _LONG_POLL_TIMEOUT,
                    "allowed_updates": json.dumps(
                        ["message", "callback_query", "my_chat_member", "guest_message"]
                    ),
                }

                response = await self._client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if not data.get("ok"):
                    logger.error("getUpdates returned non-ok: %s", data)
                    await asyncio.sleep(5)
                    continue

                for update_raw in data.get("result", []):
                    self._offset = update_raw["update_id"] + 1

                    # Route guest updates to our handler
                    if "guest_message" in update_raw:
                        await self._handle_guest_message(update_raw)
                        continue

                    # Route all other updates to python-telegram-bot
                    logger.debug("Forwarding regular update %s", update_raw.get("update_id"))
                    update = Update.de_json(update_raw, self.app.bot)
                    if update:
                        await self.app.process_update(update)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in guest polling loop")
                await asyncio.sleep(5)

    async def _handle_guest_message(self, raw_update: dict) -> None:
        """Handle a guest_message update from Bot API 10.0.

        Args:
            raw_update: The raw update dict from getUpdates containing
                a ``guest_message`` key.
        """
        guest_msg = raw_update["guest_message"]
        caller_user = guest_msg.get("guest_bot_caller_user", {})
        guest_query_id = guest_msg.get("guest_query_id", "")
        caller_id = caller_user.get("id", 0)
        text = guest_msg.get("text", "")

        request_id = uuid.uuid4().hex[:8]

        details_logger.info(
            "guest_message received",
            extra={
                "extra_data": {
                    "event": "guest_message",
                    "request_id": request_id,
                    "guest_query_id": guest_query_id,
                    "caller_id": caller_id,
                    "caller_name": caller_user.get("first_name"),
                    "caller_username": caller_user.get("username"),
                    "text": text,
                }
            },
        )

        if not is_user_allowed(caller_id):
            details_logger.info(
                "guest_message unauthorized",
                extra={
                    "extra_data": {
                        "event": "guest_message_unauthorized",
                        "request_id": request_id,
                        "caller_id": caller_id,
                    }
                },
            )
            return

        # Extract URLs from guest message text
        urls = extract_urls(text)

        # If no URLs in the message text, check the replied-to message
        if not urls:
            reply_to = guest_msg.get("reply_to_message")
            if reply_to:
                urls = extract_urls(reply_to.get("text", ""))

        # If still no URLs, tell the user
        if not urls:
            details_logger.info(
                "guest_message — no URLs found",
                extra={
                    "extra_data": {
                        "event": "guest_message_no_urls",
                        "request_id": request_id,
                        "guest_query_id": guest_query_id,
                        "caller_id": caller_id,
                        "text": text,
                    }
                },
            )
            await self.answer_guest_query(
                guest_query_id,
                _text_result("Please include a URL to download"),
            )
            return

        details_logger.info(
            "guest_message — URLs extracted",
            extra={
                "extra_data": {
                    "event": "guest_message_urls_extracted",
                    "request_id": request_id,
                    "guest_query_id": guest_query_id,
                    "caller_id": caller_id,
                    "urls": urls,
                }
            },
        )

        # Download and build result for the first URL
        url = urls[0]
        platform = detect_platform(url)

        result = await self._download_and_build_result(url, platform, guest_query_id)

        await self.answer_guest_query(guest_query_id, result)

    # -----------------------------------------------------------------------
    # Download pipeline
    # -----------------------------------------------------------------------

    async def _download_and_build_result(
        self, url: str, platform: str | None, guest_query_id: str
    ) -> dict:
        """Download media from *url* and return an InlineQueryResult dict.

        Dispatches to platform-specific downloaders for YouTube, TikTok, and
        Instagram.  Unsupported platforms fall back to gallery-dl.  Returns an
        ``_text_result`` on error so the user always gets a response.
        """
        try:
            if not platform:
                return _text_result("Unsupported platform")

            if platform == "youtube":
                return await self._download_youtube(url, guest_query_id)

            if platform == "tiktok":
                return await self._download_media_result(url, "tiktok")

            if platform == "instagram":
                return await self._download_media_result(url, "instagram")

            # Future-proofing: gallery-dl fallback for any unrecognized platform
            return await self._gallery_dl_result(url)

        except Exception as e:
            details_logger.exception(
                "guest_download_failed",
                extra={"extra_data": {"url": url, "platform": platform}},
            )
            return _text_result(f"Download failed: {e}")

    async def _download_youtube(self, url: str, guest_query_id: str) -> dict:
        """Download a YouTube video, respecting MAX_FILE_SIZE."""
        metadata = await asyncio.to_thread(get_metadata, url)
        if metadata:
            # Check size if available (size_bytes from yt-dlp)
            size_mb = 0
            if metadata.get("filesize"):
                size_mb = metadata["filesize"] / (1024 * 1024)
            elif metadata.get("filesize_approx"):
                size_mb = metadata["filesize_approx"] / (1024 * 1024)

            if size_mb > MAX_FILE_SIZE:
                return _text_result(
                    f"Video too large ({size_mb:.0f}MB, limit {MAX_FILE_SIZE}MB)"
                )

        title = (metadata.get("title", "Video") if metadata else "Video")[:64]
        output_path = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}.mp4")
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        try:
            success = await asyncio.to_thread(
                download_video, url, output_path, MAX_FILE_SIZE
            )
            if not success:
                return _text_result("YouTube download failed")

            file_id = await self._upload_to_telegram(output_path, "video")
            if not file_id:
                return _text_result("Failed to upload video to Telegram")

            return _video_result(file_id, title=title)
        finally:
            cleanup_file(output_path)

    async def _download_media_result(self, url: str, platform: str) -> dict:
        """Download TikTok/Instagram content and return appropriate result."""
        output_dir = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}")
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Try video download first
            video_path = os.path.join(output_dir, f"{platform}.mp4")
            success = await asyncio.to_thread(
                download_video, url, video_path, MAX_FILE_SIZE, platform
            )
            if success:
                file_id = await self._upload_to_telegram(video_path, "video")
                if file_id:
                    return _video_result(file_id, title=f"{platform.title()} video")

            # Try image/gallery-dl fallback
            if platform == "instagram":
                cookies = INSTAGRAM_COOKIES
            else:
                cookies = ""
            images = await asyncio.to_thread(
                download_gallery_dl_images, url, output_dir, cookies
            )
            if images:
                file_ids = []
                for img_path in images[:10]:  # Telegram max 10 per group
                    fid = await self._upload_to_telegram(img_path, "photo")
                    if fid:
                        file_ids.append(fid)
                if file_ids:
                    if len(file_ids) == 1:
                        return _photo_result(file_ids[0])
                    return _media_group_result(file_ids)

            # Try gallery-dl video fallback
            video = await asyncio.to_thread(
                download_gallery_dl_video, url, output_dir
            )
            if video:
                file_id = await self._upload_to_telegram(video, "video")
                if file_id:
                    return _video_result(file_id, title=f"{platform.title()} video")

            return _text_result("Could not download media from this URL")
        finally:
            cleanup_dir(output_dir)

    async def _gallery_dl_result(self, url: str) -> dict:
        """gallery-dl fallback for unsupported platforms."""
        output_dir = os.path.join(DOWNLOAD_DIR, f"guest_{uuid.uuid4().hex[:8]}")
        os.makedirs(output_dir, exist_ok=True)

        try:
            # Try images first
            images = await asyncio.to_thread(
                download_gallery_dl_images, url, output_dir
            )
            if images:
                file_ids = []
                for img_path in images[:10]:
                    fid = await self._upload_to_telegram(img_path, "photo")
                    if fid:
                        file_ids.append(fid)
                if file_ids:
                    if len(file_ids) == 1:
                        return _photo_result(file_ids[0])
                    return _media_group_result(file_ids)

            # Try video
            video = await asyncio.to_thread(
                download_gallery_dl_video, url, output_dir
            )
            if video:
                file_id = await self._upload_to_telegram(video, "video")
                if file_id:
                    return _video_result(file_id, title="Downloaded video")

            return _text_result("Could not download media from this URL")
        finally:
            cleanup_dir(output_dir)

    # -----------------------------------------------------------------------
    # Telegram upload
    # -----------------------------------------------------------------------

    async def _upload_to_telegram(self, file_path: str, media_type: str) -> str | None:
        """Upload a local file to Telegram and return the file_id.

        Sends the file to ``STORAGE_CHANNEL_ID`` (a private channel where the
        bot is admin) so that Telegram assigns a permanent file_id that can be
        reused in InlineQueryResult responses.
        """
        if not STORAGE_CHANNEL_ID:
            details_logger.warning(
                "upload_to_telegram skipped — STORAGE_CHANNEL_ID not configured",
                extra={"extra_data": {"file_path": file_path}},
            )
            return None

        url = _API_BASE.format(token=self.bot_token, method=f"send{media_type.capitalize()}")

        try:
            with open(file_path, "rb") as f:
                if media_type == "video":
                    files = {"video": f}
                elif media_type == "photo":
                    files = {"photo": f}
                else:
                    files = {"document": f}
                data = {"chat_id": STORAGE_CHANNEL_ID}

                response = await self._client.post(url, data=data, files=files)
                result = response.json()

                if not result.get("ok"):
                    details_logger.warning(
                        "upload_to_telegram failed",
                        extra={"extra_data": {"error": result.get("description"), "file_path": file_path}},
                    )
                    return None

                # Extract file_id from the response
                msg = result.get("result", {})
                if media_type == "video":
                    return msg.get("video", {}).get("file_id")
                elif media_type == "photo":
                    return msg.get("photo", {}).get("file_id")
                else:
                    return msg.get("document", {}).get("file_id")

        except Exception:
            details_logger.exception(
                "upload_to_telegram exception",
                extra={"extra_data": {"file_path": file_path, "media_type": media_type}},
            )
            return None

    # -----------------------------------------------------------------------
    # answerGuestQuery API call
    # -----------------------------------------------------------------------

    async def answer_guest_query(self, guest_query_id: str, result: dict) -> None:
        """POST answerGuestQuery to the Telegram Bot API."""
        url = _API_BASE.format(token=self.bot_token, method="answerGuestQuery")

        payload = {
            "guest_query_id": guest_query_id,
            "result": json.dumps(result),
        }

        try:
            response = await self._client.post(url, json=payload)
            data = response.json()
            if not data.get("ok"):
                details_logger.warning(
                    "answerGuestQuery failed",
                    extra={
                        "extra_data": {
                            "guest_query_id": guest_query_id,
                            "error": data.get("description"),
                        }
                    },
                )
        except Exception:
            details_logger.exception(
                "answerGuestQuery exception",
                extra={"extra_data": {"guest_query_id": guest_query_id}},
            )
