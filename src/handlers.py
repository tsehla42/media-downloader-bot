import logging
import os
import uuid
from telegram import Update
from telegram.ext import ContextTypes

_log = logging.getLogger(__name__)

from config import DOWNLOAD_DIR
from utils import is_valid_url, extract_urls, cleanup_file
from platforms import detect_platform
from platforms.youtube import handle_youtube, handle_ytmusic, AUDIO_TITLE_MAX, _store_download_metadata
from platforms.instagram import handle_instagram
from platforms.tiktok import handle_tiktok
from downloader import get_metadata, download_audio
from commands import get_caption_for_user
from auth import is_authorized, is_group_chat
from logging_config import (
    with_request_logging,
    log_bot_added_to_chat,
    log_bot_removed_from_chat,
    log_bot_status_changed,
)
from telegram_utils import typing_indicator


async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot membership changes (added, removed, promoted, demoted)."""
    chat_member_update = update.my_chat_member
    if not chat_member_update:
        return

    chat = chat_member_update.chat
    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status
    from_user = chat_member_update.from_user

    # Bot was added to chat
    if old_status in ("left", "kicked"):
        log_bot_added_to_chat(chat, from_user)
        return

    # Bot was removed from chat
    if new_status in ("left", "kicked"):
        log_bot_removed_from_chat(chat, from_user)
        return

    # Bot was promoted to admin
    if old_status == "member" and new_status == "administrator":
        log_bot_status_changed(chat, from_user, old_status, new_status)
        return

    # Bot was demoted from admin
    if old_status == "administrator" and new_status == "member":
        log_bot_status_changed(chat, from_user, old_status, new_status)
        return


@with_request_logging
async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_params = {"message_id": update.message.message_id}

    if not is_authorized(update):
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            "You are not authorized to use this bot",
            reply_parameters=reply_params,
        )
        return

    text = update.message.text.replace("/audio", "").strip()
    if not text:
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            "Usage: /audio <url>",
            reply_parameters=reply_params,
        )
        return

    urls = extract_urls(text)
    if not urls:
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            "Please provide a valid URL",
            reply_parameters=reply_params,
        )
        return

    url = urls[0]
    platform = detect_platform(url)
    context.user_data["_platform"] = platform or ""
    if not platform:
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            "Unsupported platform. Use /help to see supported sites",
            reply_parameters=reply_params,
        )
        return

    # Fetch metadata for title (used in filename and reply_audio title)
    metadata = get_metadata(url)
    title = metadata.get("title") if metadata else None

    tmp_id = uuid.uuid4().hex[:8]
    filename = f"{title}.{tmp_id}.mp3" if title else f"{tmp_id}.mp3"
    output_path = os.path.join(DOWNLOAD_DIR, filename)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    async with typing_indicator(update.message.chat.id, context.bot):
        try:
            _log.info("audio: downloading %s -> %s", url, output_path)
            success = download_audio(url, output_path)
            if success and os.path.isfile(output_path):
                _log.info("audio: download ok, size=%d bytes", os.path.getsize(output_path))
                with open(output_path, "rb") as f:
                    if title:
                        await update.message.reply_audio(
                            audio=f,
                            title=title[:AUDIO_TITLE_MAX],
                            reply_parameters=reply_params,
                        )
                    else:
                        await update.message.reply_audio(
                            audio=f,
                            reply_parameters=reply_params,
                        )
                _store_download_metadata(context, "audio", output_path)
            else:
                _log.warning("audio: download failed for %s", url)
                context.user_data["_request_success"] = False
                await update.message.reply_text(
                    "Failed to download audio. Check the URL and try again",
                    reply_parameters=reply_params,
                )
        except Exception as e:
            _log.error("audio: error for %s: %s", url, e, exc_info=True)
            context.user_data["_request_success"] = False
            await update.message.reply_text(
                f"Error: {e}",
                reply_parameters=reply_params,
            )
        finally:
            cleanup_file(output_path)


async def _download_and_send(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str,
    silent: bool = True, reply_to_message_id: int | None = None,
) -> bool:
    """Download content from URL and send to chat.

    Args:
        silent: If True, suppress error messages in group chats (default).
                If False, always reply with error messages (used by reply-to-retry).
        reply_to_message_id: If set, reply to this message ID instead of update.message.
                            Used by reply-to-retry to reply to the original link message.

    Returns:
        True if content was sent successfully, False otherwise.
    """
    from config import MAX_FILE_SIZE

    if reply_to_message_id:
        reply_params = {"message_id": reply_to_message_id}
    else:
        reply_params = {"message_id": update.message.message_id}

    platform = detect_platform(url)
    context.user_data["_platform"] = platform or ""

    if not platform:
        context.user_data["_request_success"] = False
        if not (is_group_chat(update) and silent):
            await update.message.reply_text(
                "Unsupported platform. I support YouTube, TikTok, and Instagram",
                reply_parameters=reply_params,
            )
        return False

    # Instagram and TikTok handle their own metadata and content fetching
    if platform == "instagram":
        handled = await handle_instagram(update, context, url)
        if not handled:
            context.user_data["_request_success"] = False
            if not (is_group_chat(update) and silent):
                await update.message.reply_text(
                    "Could not fetch post. The content may be private or the URL is invalid",
                    reply_parameters=reply_params,
                )
        return handled

    if platform == "tiktok":
        handled = await handle_tiktok(update, context, url)
        if not handled:
            context.user_data["_request_success"] = False
            if not (is_group_chat(update) and silent):
                await update.message.reply_text(
                    "Could not fetch post. The content may be private or the URL is invalid",
                    reply_parameters=reply_params,
                )
        return handled

    # YouTube / YouTube Music: fetch metadata first
    metadata = get_metadata(url)
    if not metadata:
        context.user_data["_request_success"] = False
        _log.info("youtube_metadata_failed url=%s", url)
        if not (is_group_chat(update) and silent):
            await update.message.reply_text(
                "Could not fetch post. The content may be private or the URL is invalid",
                reply_parameters=reply_params,
            )
        return False

    title = metadata.get("title", "video")
    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        if "music.youtube.com" in url:
            await handle_ytmusic(
                update, context, url, metadata, title,
                base, output_path, reply_params,
            )
            return True

        if platform == "youtube":
            # Check file size before downloading
            estimated_size = metadata.get("filesize") or metadata.get("filesize_approx")
            if estimated_size is not None:
                size_mb = round(estimated_size / (1024 * 1024), 2)
                if estimated_size > MAX_FILE_SIZE * 1024 * 1024:
                    _log.info(
                        "youtube_skipped_large title=%s size_mb=%.2f",
                        title, size_mb,
                    )
                    context.user_data["_request_success"] = False
                    if not (is_group_chat(update) and silent):
                        await update.message.reply_text(
                            "This video is above Telegram's 50MB limit",
                            reply_parameters=reply_params,
                        )
                    return False
                _log.info(
                    "youtube_size_check title=%s size_mb=%.2f passed=true",
                    title, size_mb,
                )
            else:
                _log.info(
                    "youtube_size_check title=%s size_mb=None passed=true",
                    title,
                )

            caption = get_caption_for_user(update.message.from_user.id, title)
            video_ok = await handle_youtube(
                update, context, url, base, output_path, caption, reply_params,
            )
            if not video_ok:
                context.user_data["_request_success"] = False
                if not (is_group_chat(update) and silent):
                    await update.message.reply_text(
                        "Download failed",
                        reply_parameters=reply_params,
                    )
            return video_ok

        context.user_data["_request_success"] = False
        if not (is_group_chat(update) and silent):
            await update.message.reply_text(
                "Download failed",
                reply_parameters=reply_params,
            )
        return False
    except Exception as e:
        context.user_data["_request_success"] = False
        if not (is_group_chat(update) and silent):
            await update.message.reply_text(
                f"Error: {e}",
                reply_parameters=reply_params,
            )
        return False
    finally:
        for ext in ["mp4", "webm", "mkv", "mp3", "m4a"]:
            cleanup_file(f"{base}.{ext}")


async def handle_reply_to_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle replies to messages containing URLs when bot is mentioned.

    Allows users to retry a download by replying to an old message with
    a link and mentioning the bot. All platforms supported.
    """
    if not update.message or not update.message.text:
        return

    # Check if this is a reply
    if not update.message.reply_to_message:
        return

    # Check if bot is mentioned in the reply text
    bot_username = context.bot_data.get("bot_username", "")
    if not bot_username or f"@{bot_username}" not in update.message.text:
        return

    # Check authorization
    if not is_authorized(update):
        await update.message.reply_text(
            "You are not authorized to use this bot",
            reply_parameters={"message_id": update.message.message_id},
        )
        return

    # Extract URL from the replied-to message
    replied_text = update.message.reply_to_message.text or ""
    urls = extract_urls(replied_text)
    if not urls:
        return

    url = urls[0]

    # Log the retry attempt
    _log.info(
        "reply_to_retry url=%s user=%s chat=%s",
        url,
        getattr(update.message.from_user, "id", None),
        update.message.chat.id,
    )

    # Process with silent=False (errors always shown)
    await _download_and_send(
        update, context, url,
        silent=False,
        reply_to_message_id=update.message.reply_to_message.message_id,
    )


@with_request_logging
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    if not is_authorized(update):
        await update.message.reply_text(
            "You are not authorized to use this bot",
            reply_parameters={"message_id": update.message.message_id},
        )
        return

    text = update.message.text.strip()

    if text.startswith("/audio"):
        await audio_command(update, context)
        return

    if not is_valid_url(text):
        return

    urls = extract_urls(text)
    if not urls:
        # In P2P: show error. In groups: silently ignore.
        if not is_group_chat(update):
            await update.message.reply_text(
                "Please send a valid URL",
                reply_parameters={"message_id": update.message.message_id},
            )
        return

    # Filter to supported platforms only
    supported_urls = [url for url in urls if detect_platform(url)]

    # In groups: ignore if no supported URLs (no error message)
    if is_group_chat(update) and not supported_urls:
        return

    # In P2P: show error if no valid URLs
    if not is_group_chat(update) and not supported_urls:
        await update.message.reply_text(
            "Unsupported platform. I support YouTube, TikTok, and Instagram",
            reply_parameters={"message_id": update.message.message_id},
        )
        return

    # Split YouTube from non-YouTube for typing indicator handling
    youtube_urls = [url for url in supported_urls if detect_platform(url) == "youtube"]
    non_youtube_urls = [url for url in supported_urls if detect_platform(url) != "youtube"]

    # YouTube: no typing during metadata fetch, handled inside _download_and_send
    for url in youtube_urls:
        await _download_and_send(update, context, url)

    # Non-YouTube: typing wraps full flow (current behavior)
    if non_youtube_urls:
        async with typing_indicator(update.message.chat.id, context.bot):
            for url in non_youtube_urls:
                await _download_and_send(update, context, url)
