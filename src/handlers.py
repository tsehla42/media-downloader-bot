import os
import re
import time
import uuid
from telegram import Update
from telegram.ext import ContextTypes

from config import DOWNLOAD_DIR
from utils import is_valid_url, extract_urls, cleanup_file, cleanup_dir


def _log_extra(context, url: str) -> dict:
    """Build extra fields for structured detail logging in handlers."""
    return {
        "url": url,
        "request_id": context.user_data.get("request_id", ""),
        "platform": context.user_data.get("_platform", ""),
    }
from platforms import detect_platform
from platforms.youtube import handle_youtube, handle_ytmusic, AUDIO_TITLE_MAX, _store_download_metadata
from platforms.instagram import handle_instagram
from platforms.tiktok import handle_tiktok
from downloader import get_metadata, download_audio, download_gallery_dl_images, download_gallery_dl_video
from commands import get_caption_for_user
from auth import is_authorized, is_group_chat, was_notified, mark_notified, is_bot_admin
from logging_config import (
    with_request_logging,
    log_bot_added_to_chat,
    log_bot_rejected_group_addition,
    log_bot_removed_from_chat,
    log_bot_status_changed,
    log_admin_rights_changed,
    log_custom_title_changed,
    log_user_blocked_bot,
    log_user_unblocked_bot,
    log_unauthorized_access,
    _extract_admin_rights,
    log_request_received,
    log_request_completed,
    set_current_request_id,
    details_logger,
)
from telegram_utils import typing_indicator, send_images


async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot membership changes (added, removed, promoted, demoted, blocked)."""
    chat_member_update = update.my_chat_member
    if not chat_member_update:
        return

    chat = chat_member_update.chat
    old_status = chat_member_update.old_chat_member.status
    new_status = chat_member_update.new_chat_member.status
    from_user = chat_member_update.from_user

    # User blocked bot in private chat (status becomes "kicked")
    if new_status == "kicked" and getattr(chat, "type", None) == "private":
        log_user_blocked_bot(chat, from_user)
        return

    # User unblocked bot in private chat (status was "kicked", now "member")
    if old_status == "kicked" and new_status == "member" and getattr(chat, "type", None) == "private":
        log_user_unblocked_bot(chat, from_user)
        return

    # Bot removed from chat (any status → left/kicked)
    if new_status in ("left", "kicked"):
        log_bot_removed_from_chat(chat, from_user)
        return

    old_admin_rights = _extract_admin_rights(chat_member_update.old_chat_member)
    new_admin_rights = _extract_admin_rights(chat_member_update.new_chat_member)

    # Bot promoted to admin (was non-admin, now administrator with rights)
    if old_status != "administrator" and new_status == "administrator":
        log_admin_rights_changed(chat, from_user, None, new_admin_rights, "bot_added_as_admin")
        return

    # Bot demoted from admin (was administrator, now non-admin)
    if old_status == "administrator" and new_status != "administrator":
        log_bot_status_changed(chat, from_user, old_status, new_status)
        return

    # Admin rights changed (was admin, still admin, but rights differ)
    if old_status == "administrator" and new_status == "administrator":
        if old_admin_rights != new_admin_rights:
            # Custom title only change → separate lightweight event
            old_title = (old_admin_rights or {}).get("custom_title")
            new_title = (new_admin_rights or {}).get("custom_title")
            # Only compare explicitly set values (skip None/MagicMock which means "not set")
            other_changes = {}
            for k, old_val in (old_admin_rights or {}).items():
                if k == "custom_title":
                    continue
                new_val = (new_admin_rights or {}).get(k)
                if old_val is None and new_val is None:
                    continue
                if old_val != new_val:
                    other_changes[k] = (old_val, new_val)
            if not other_changes and old_title != new_title:
                log_custom_title_changed(chat, from_user, old_title, new_title)
            else:
                # Check if any rights were removed (restriction)
                has_removals = any(
                    old_val is True and ((new_admin_rights or {}).get(k) is not True)
                    for k, old_val in (old_admin_rights or {}).items()
                    if k != "custom_title"
                )
                event = "bot_restrictions_changed" if has_removals else "bot_admin_rights_changed"
                log_admin_rights_changed(chat, from_user, old_admin_rights, new_admin_rights, event)
        return

    # Bot added to chat (non-admin, e.g. added as regular member)
    # Skip private chats — /start command handles P2P user tracking
    if old_status in ("left", "kicked") and getattr(chat, "type", None) != "private":
        # Check if user is admin - if not, reject and leave
        if not is_bot_admin(from_user.id):
            log_bot_rejected_group_addition(chat, from_user)
            await context.bot.send_message(
                chat.id,
                "Only bot admins can add me to groups",
            )
            await context.bot.leave_chat(chat.id)
            return
        log_bot_added_to_chat(chat, from_user)
        return


@with_request_logging
async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_params = {"message_id": update.message.message_id}

    if not is_authorized(update):
        if not is_group_chat(update):
            user_id = update.message.from_user.id
            if not was_notified(user_id):
                await update.message.reply_text(
                    "You are not authorized to use this bot",
                    reply_parameters=reply_params,
                )
                mark_notified(user_id)
                log_unauthorized_access(update.message.from_user, update.message.chat, "/audio")
        context.user_data["_request_success"] = False
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
        extra = _log_extra(context, url)
        try:
            details_logger.info("audio: downloading", extra=extra)
            success = download_audio(url, output_path)
            if success and os.path.isfile(output_path):
                details_logger.info("audio: download ok, size=%d bytes", os.path.getsize(output_path), extra=extra)
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
                details_logger.warning("audio: download failed", extra=extra)
                context.user_data["_request_success"] = False
                await update.message.reply_text(
                    "Failed to download audio. Check the URL and try again",
                    reply_parameters=reply_params,
                )
        except Exception as e:
            details_logger.error("audio: error: %s", e, exc_info=True, extra=extra)
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
    extra = _log_extra(context, url)
    if not metadata:
        context.user_data["_request_success"] = False
        details_logger.info("youtube_metadata_failed", extra=extra)
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
                    details_logger.info(
                        "youtube_skipped_large, title=%s, size_mb=%.2f",
                        title, size_mb,
                        extra=extra,
                    )
                    context.user_data["_request_success"] = False
                    if not (is_group_chat(update) and silent):
                        await update.message.reply_text(
                            "This video is above Telegram's 50MB limit",
                            reply_parameters=reply_params,
                        )
                    return False
                details_logger.info(
                    "youtube_size_check, title=%s, size_mb=%.2f, passed=true",
                    title, size_mb,
                    extra=extra,
                )
            else:
                details_logger.info(
                    "youtube_size_check, title=%s, size_mb=None, passed=true",
                    title,
                    extra=extra,
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


async def handle_gallery_dl_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> bool:
    """Try gallery-dl for unsupported platforms. Silent on failure.

    Returns True if content was sent, False otherwise.
    """
    reply_params = {"message_id": update.message.message_id}

    # Set platform from URL domain for logging
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    context.user_data["_platform"] = re.sub(r"^www\.", "", host)

    # Try images first
    tmp_id = uuid.uuid4().hex[:8]
    out_dir = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    try:
        try:
            images = download_gallery_dl_images(url, out_dir, "")
        except Exception as e:
            details_logger.warning("gallery-dl images failed: %s", e)
            images = []
        if images:
            try:
                total_size = await send_images(update.message, images, reply_params)
            except Exception as e:
                details_logger.error("gallery-dl image send failed: %s", e)
                context.user_data["_request_success"] = False
                return False
            context.user_data["_content_type"] = "image"
            context.user_data["_file_size_mb"] = round(total_size / (1024 * 1024), 2) if total_size > 0 else None
            context.user_data["_request_success"] = True
            return True
    finally:
        cleanup_dir(out_dir)

    # Try video
    tmp_id = uuid.uuid4().hex[:8]
    out_dir = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    try:
        try:
            video = download_gallery_dl_video(url, out_dir)
        except Exception as e:
            details_logger.warning("gallery-dl video failed: %s", e)
            video = None
        if video:
            try:
                with open(video, "rb") as f:
                    await update.message.reply_video(
                        video=f,
                        reply_parameters=reply_params,
                    )
            except Exception as e:
                details_logger.error("gallery-dl video send failed: %s", e)
                context.user_data["_request_success"] = False
                return False
            context.user_data["_content_type"] = "video"
            try:
                context.user_data["_file_size_mb"] = round(os.path.getsize(video) / (1024 * 1024), 2)
            except OSError:
                pass
            context.user_data["_request_success"] = True
            return True
    finally:
        cleanup_dir(out_dir)

    context.user_data["_request_success"] = False
    return False


@with_request_logging
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    if not is_authorized(update):
        if not is_group_chat(update):
            user_id = update.message.from_user.id
            if not was_notified(user_id):
                await update.message.reply_text(
                    "You are not authorized to use this bot",
                    reply_parameters={"message_id": update.message.message_id},
                )
                mark_notified(user_id)
                log_unauthorized_access(update.message.from_user, update.message.chat, "url")
        return  # silently ignore in groups or if already told

    text = update.message.text.strip()

    # Reply-to-retry: user replies to an old message with a URL and mentions the bot.
    # Check this BEFORE the regular URL flow so it takes priority.
    if update.message.reply_to_message:
        bot_username = context.bot_data.get("bot_username", "")
        if bot_username and f"@{bot_username}" in text:
            replied_text = update.message.reply_to_message.text or ""
            retry_urls = extract_urls(replied_text)
            if retry_urls:
                user = update.message.from_user
                chat = update.message.chat
                request_id = uuid.uuid4().hex[:8]
                context.user_data["request_id"] = request_id
                set_current_request_id(request_id)

                log_request_received(
                    request_id=request_id,
                    url=retry_urls[0],
                    user=user,
                    chat=chat,
                    event="reply_to_retry",
                )

                start_time = time.time()

                async with typing_indicator(update.message.chat.id, context.bot):
                    success = await _download_and_send(
                        update, context, retry_urls[0],
                        silent=False,
                        reply_to_message_id=update.message.reply_to_message.message_id,
                    )

                duration_ms = int((time.time() - start_time) * 1000)
                platform = context.user_data.get("_platform", "")
                content_type = context.user_data.get("_content_type")
                file_size_mb = context.user_data.get("_file_size_mb")
                log_request_completed(
                    request_id=request_id,
                    url=retry_urls[0],
                    platform=platform,
                    duration_ms=duration_ms,
                    success=success,
                    content_type=content_type,
                    file_size_mb=file_size_mb,
                    user=user,
                    chat=chat,
                    event="reply_to_retry",
                )
                return

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

    # Split into supported (YT/TT/IG) and unsupported URLs
    supported_urls = [url for url in urls if detect_platform(url)]
    unsupported_urls = [url for url in urls if not detect_platform(url)]

    # In groups: ignore if nothing to process
    if is_group_chat(update) and not supported_urls and not unsupported_urls:
        return

    # In P2P: error shown after gallery-dl attempt if needed (see below)

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

    # Process unsupported URLs via gallery-dl fallback
    if unsupported_urls:
        any_handled = False
        for url in unsupported_urls:
            handled = await handle_gallery_dl_fallback(update, context, url)
            if handled:
                any_handled = True
        if not any_handled and not is_group_chat(update) and not supported_urls:
            await update.message.reply_text(
                "Unsupported platform. I support YouTube, TikTok, and Instagram",
                reply_parameters={"message_id": update.message.message_id},
            )
