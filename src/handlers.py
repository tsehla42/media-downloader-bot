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


async def _reply_failure(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
    skip_reason: str,
    reply_params: dict,
    silent: bool = True,
) -> None:
    """Mark request as failed, set skip reason, and optionally reply with error message.

    Group suppression rules by platform:
    - TikTok/Instagram: show all errors
    - YouTube: suppress size_limit only
    - Unsupported/other: suppress all in groups
    """
    context.user_data["_request_success"] = False
    context.user_data["_skip_reason"] = skip_reason
    if is_group_chat(update) and silent:
        platform = context.user_data.get("_platform", "")
        if platform in ("tiktok", "instagram"):
            pass  # show all errors
        elif platform == "youtube" and skip_reason == "size_limit":
            return  # suppress size limit for YouTube
        else:
            return  # suppress everything else in groups
    await update.message.reply_text(
        message,
        reply_parameters=reply_params,
    )


async def _handle_metadata_failure(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    silent: bool,
    reply_params: dict,
    log_event: str,
    user_message: str,
) -> None:
    """Handle metadata fetch failure with logging and optional reply.

    Group suppression follows same rules as _reply_failure():
    TikTok/Instagram show all errors, YouTube/others suppress in groups.
    """
    extra = _log_extra(context, url)
    context.user_data["_request_success"] = False
    context.user_data["_skip_reason"] = "metadata_failed"
    details_logger.info(log_event, extra=extra)
    if is_group_chat(update) and silent:
        platform = context.user_data.get("_platform", "")
        if platform in ("tiktok", "instagram"):
            pass  # show all errors
        else:
            return  # suppress for YouTube and others in groups
    await update.message.reply_text(
        user_message,
        reply_parameters=reply_params,
    )


from platforms import detect_platform, extract_domain
from utils import get_gallery_dl_domains, get_ytdlp_domains
from platforms.youtube import handle_youtube, handle_ytmusic, AUDIO_TITLE_MAX, _store_download_metadata
from platforms.instagram import handle_instagram
from platforms.tiktok import handle_tiktok
from downloader import get_metadata, download_audio, download_video, download_gallery_dl_images, download_gallery_dl_video, DownloadAuthRequired, DownloadError, VIDEO_FORMAT_SELECTOR
from messages import (
    MSG_UNSUPPORTED_PLATFORM, MSG_INVALID_URL,
    MSG_LOGIN_REQUIRED, MSG_FETCH_FAILED, MSG_SIZE_LIMIT,
    MSG_METADATA_FAILED, MSG_DOWNLOAD_FAILED, MSG_AUDIO_USAGE, MSG_AUDIO_FAILED,
    MSG_ONLY_ADMINS_CAN_ADD,
)
from commands import get_caption_for_user
from auth import is_group_chat, is_private_chat, is_bot_admin, _is_allowed, reject_if_unauthorized
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

    if new_status == "kicked" and is_private_chat(chat):
        log_user_blocked_bot(chat, from_user)
        return

    if old_status == "kicked" and new_status == "member" and is_private_chat(chat):
        log_user_unblocked_bot(chat, from_user)
        return

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
    if old_status in ("left", "kicked") and not is_private_chat(chat):
        # Check if user is admin - if not, reject and leave
        if not is_bot_admin(from_user.id):
            log_bot_rejected_group_addition(chat, from_user)
            await context.bot.send_message(
                chat.id,
                MSG_ONLY_ADMINS_CAN_ADD,
            )
            await context.bot.leave_chat(chat.id)
            return
        log_bot_added_to_chat(chat, from_user)
        return


@with_request_logging
async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reply_params = {"message_id": update.message.message_id, "allow_sending_without_reply": True}

    if await reject_if_unauthorized(update, "/audio", reply_parameters=reply_params, group_silent=True):
        context.user_data["_request_success"] = False
        return

    text = update.message.text.replace("/audio", "").strip()
    if not text:
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            MSG_AUDIO_USAGE,
            reply_parameters=reply_params,
        )
        return

    urls = extract_urls(text)
    if not urls:
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            MSG_INVALID_URL,
            reply_parameters=reply_params,
        )
        return

    url = urls[0]
    platform = detect_platform(url)
    context.user_data["_platform"] = platform or ""
    if not platform:
        context.user_data["_request_success"] = False
        await update.message.reply_text(
            MSG_UNSUPPORTED_PLATFORM,
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
                    MSG_AUDIO_FAILED,
                    reply_parameters=reply_params,
                )
        except DownloadError as e:
            details_logger.warning("audio: download error: %s", e.raw_error, extra=extra)
            context.user_data["_request_success"] = False
            await update.message.reply_text(
                e.user_message,
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
        reply_params = {"message_id": reply_to_message_id, "allow_sending_without_reply": True}
    else:
        reply_params = {"message_id": update.message.message_id, "allow_sending_without_reply": True}

    platform = detect_platform(url)
    context.user_data["_platform"] = platform or ""

    if not platform:
        # Check if domain is in yt-dlp supported domains
        ytdlp_domains = get_ytdlp_domains()
        domain = extract_domain(url)
        if domain in ytdlp_domains:
            # Generic yt-dlp download for non-yt/tt/ig sites
            metadata = get_metadata(url)
            if not metadata:
                await _handle_metadata_failure(update, context, url, silent, reply_params, "ytdlp_metadata_failed", MSG_METADATA_FAILED)
                return False

            title = metadata.get("title", "video")
            estimated_size = metadata.get("filesize") or metadata.get("filesize_approx")
            if estimated_size and estimated_size > MAX_FILE_SIZE * 1024 * 1024:
                await _reply_failure(update, context, MSG_SIZE_LIMIT, "size_limit", reply_params, silent)
                return False

            tmp_id = uuid.uuid4().hex[:8]
            output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
            base = os.path.join(DOWNLOAD_DIR, tmp_id)
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)

            try:
                video_ok = download_video(url, output_path)
                if not video_ok:
                    await _reply_failure(update, context, MSG_DOWNLOAD_FAILED, "download_failed", reply_params, silent)
                    return False

                for ext in ["mp4", "webm", "mkv"]:
                    filepath = f"{base}.{ext}"
                    if os.path.isfile(filepath):
                        with open(filepath, "rb") as f:
                            await update.message.reply_video(
                                video=f,
                                reply_parameters=reply_params,
                                supports_streaming=True,
                            )
                        context.user_data["_content_type"] = "video"
                        context.user_data["_file_size_mb"] = round(os.path.getsize(filepath) / (1024 * 1024), 2)
                        return True
                return False
            finally:
                for ext in ["mp4", "webm", "mkv"]:
                    cleanup_file(f"{base}.{ext}")

        await _reply_failure(update, context, MSG_UNSUPPORTED_PLATFORM, "unsupported", reply_params, silent)
        return False

    # Instagram and TikTok handle their own metadata and content fetching
    if platform == "instagram":
        try:
            handled = await handle_instagram(update, context, url)
        except DownloadAuthRequired:
            await _reply_failure(update, context, MSG_LOGIN_REQUIRED, "auth_required", reply_params, silent)
            return False
        except DownloadError as e:
            extra = _log_extra(context, url)
            details_logger.warning("instagram: download error: %s", e.raw_error, extra=extra)
            await _reply_failure(update, context, e.user_message, "fetch_failed", reply_params, silent)
            return False
        if not handled:
            await _reply_failure(update, context, MSG_FETCH_FAILED, "fetch_failed", reply_params, silent)
        return handled

    if platform == "tiktok":
        try:
            handled = await handle_tiktok(update, context, url)
        except DownloadAuthRequired:
            await _reply_failure(update, context, MSG_LOGIN_REQUIRED, "auth_required", reply_params, silent)
            return False
        except DownloadError as e:
            extra = _log_extra(context, url)
            details_logger.warning("tiktok: download error: %s", e.raw_error, extra=extra)
            await _reply_failure(update, context, e.user_message, "fetch_failed", reply_params, silent)
            return False
        if not handled:
            await _reply_failure(update, context, MSG_FETCH_FAILED, "fetch_failed", reply_params, silent)
        return handled

    # YouTube / YouTube Music: fetch metadata first
    try:
        metadata = get_metadata(url, format_selector=VIDEO_FORMAT_SELECTOR)
    except DownloadAuthRequired:
        await _reply_failure(update, context, MSG_LOGIN_REQUIRED, "auth_required", reply_params, silent)
        return False
    extra = _log_extra(context, url)
    if not metadata:
        await _handle_metadata_failure(update, context, url, silent, reply_params, "youtube_metadata_failed", MSG_FETCH_FAILED)
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
                    await _reply_failure(update, context, MSG_SIZE_LIMIT, "size_limit", reply_params, silent)
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
                await _reply_failure(update, context, MSG_DOWNLOAD_FAILED, "download_failed", reply_params, silent)
            return video_ok

        await _reply_failure(update, context, MSG_DOWNLOAD_FAILED, "download_failed", reply_params, silent)
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
    reply_params = {"message_id": update.message.message_id, "allow_sending_without_reply": True}

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
                        supports_streaming=True,
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

    if await reject_if_unauthorized(update, "url", reply_parameters={"message_id": update.message.message_id, "allow_sending_without_reply": True}, group_silent=True):
        return

    # Unauthorized user replying to bot message in a group — silently ignore
    if (is_group_chat(update)
        and update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.is_bot
        and not _is_allowed(update.message.from_user.id)):
        return

    text = update.message.text.strip()
    context.user_data["_platform"] = ""

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
                    event="reply_to_retry_received",
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
                    event="reply_to_retry_completed",
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
                MSG_INVALID_URL,
                reply_parameters={"message_id": update.message.message_id, "allow_sending_without_reply": True},
            )
        return

    # Split URLs by domain support
    ytdlp_domains = get_ytdlp_domains()
    gallery_dl_domains = get_gallery_dl_domains()

    # Categorize URLs
    youtube_urls = []
    other_ytdlp_urls = []
    gallery_dl_urls = []
    unsupported_urls = []

    for url in urls:
        domain = extract_domain(url)
        platform = detect_platform(url)
        if platform == "youtube":
            # Silently skip pure playlist URLs (list= without a specific video v=)
            if "list=" in url and "v=" not in url:
                context.user_data["_skip_reason"] = "playlist"
                continue
            youtube_urls.append(url)
        elif platform in ("tiktok", "instagram"):
            # TikTok and Instagram are handled by platform-specific handlers
            other_ytdlp_urls.append(url)
        elif domain in ytdlp_domains:
            other_ytdlp_urls.append(url)
        elif domain in gallery_dl_domains:
            gallery_dl_urls.append(url)
        else:
            unsupported_urls.append(url)

    # In groups: ignore if nothing to process
    if is_group_chat(update) and not youtube_urls and not other_ytdlp_urls and not gallery_dl_urls and not unsupported_urls:
        return

    # YouTube: no typing during metadata fetch, handled inside _download_and_send
    for url in youtube_urls:
        await _download_and_send(update, context, url)

    # Other supported URLs: typing wraps full flow
    if other_ytdlp_urls:
        async with typing_indicator(update.message.chat.id, context.bot):
            for url in other_ytdlp_urls:
                await _download_and_send(update, context, url)

    # Process gallery-dl URLs
    if gallery_dl_urls:
        any_handled = False
        for url in gallery_dl_urls:
            handled = await handle_gallery_dl_fallback(update, context, url)
            if handled:
                any_handled = True
        if not any_handled and not is_group_chat(update) and not youtube_urls and not other_ytdlp_urls:
            context.user_data["_skip_reason"] = "fetch_failed"
            await update.message.reply_text(
                MSG_UNSUPPORTED_PLATFORM,
                reply_parameters={"message_id": update.message.message_id, "allow_sending_without_reply": True},
            )
    elif unsupported_urls and not is_group_chat(update) and not youtube_urls and not other_ytdlp_urls and not gallery_dl_urls:
        # All URLs are unsupported
        context.user_data["_skip_reason"] = "unsupported"
        await update.message.reply_text(
            MSG_UNSUPPORTED_PLATFORM,
            reply_parameters={"message_id": update.message.message_id, "allow_sending_without_reply": True},
        )
