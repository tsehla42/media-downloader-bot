"""YouTube and YouTube Music download logic."""

import asyncio
import os
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from downloader import download_video, download_audio
from commands import get_caption_for_user
from telegram_utils import typing_indicator
from utils import cleanup_file, find_downloaded_file, cleanup_video_files, make_video_tmp_path
from messages import MSG_DOWNLOAD_FAILED, MSG_YTMUSIC_AUDIO_FAILED, MSG_YTMUSIC_VIDEO_FAILED, MSG_YTMUSIC_UNKNOWN_CHOICE, MSG_YTMUSIC_REQUEST_EXPIRED

from logging_config import details_logger as _log

AUDIO_TITLE_MAX = 64  # Telegram Bot API limit for reply_audio title

# Pending YouTube Music requests: shared across all users
# _ytmusic_pending[msg_id] = {"url": str, "title": str, "timestamp": float}
_ytmusic_pending: dict[int, dict] = {}
YTMUSIC_REQUEST_TTL = 300  # 5 minutes


def _has_video_available(metadata: dict) -> bool:
    """Check if real video streams exist by scanning format codecs.

    Each format has vcodec (video codec). Audio-only formats have vcodec='none'.
    If ALL formats have vcodec='none', no music video exists on YouTube.
    """
    formats = metadata.get("formats", [])
    for f in formats:
        vcodec = f.get("vcodec")
        if vcodec and vcodec != "none":
            return True
    return False


async def _download_and_send_video(
    url: str, base: str, output_path: str,
    caption: str, reply_params: dict, message, context: ContextTypes.DEFAULT_TYPE = None
) -> bool:
    success = download_video(url, output_path, MAX_FILE_SIZE)
    if not success:
        return False

    downloaded = find_downloaded_file(base)

    if not downloaded:
        return False

    with open(downloaded, "rb") as f:
        await message.reply_video(
            video=f,
            caption=caption,
            reply_parameters=reply_params,
            supports_streaming=True,
        )
    if context:
        _store_download_metadata(context, "video", downloaded)
    return True


def _store_download_metadata(context: ContextTypes.DEFAULT_TYPE, content_type: str, file_path: str) -> None:
    context.user_data["_content_type"] = content_type
    try:
        if os.path.isfile(file_path):
            file_size_bytes = os.path.getsize(file_path)
            context.user_data["_file_size_mb"] = round(file_size_bytes / (1024 * 1024), 2)
    except OSError:
        pass


async def handle_ytmusic(
    update, context: ContextTypes.DEFAULT_TYPE, url: str,
    metadata: dict, title: str, base: str, output_path: str, reply_params: dict,
) -> None:
    """Handle YouTube Music URL: show format picker or download audio directly."""
    if _has_video_available(metadata):
        # Show inline keyboard for format selection
        msg_id = update.message.message_id
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Audio", callback_data=f"ytm|{msg_id}|audio"),
            InlineKeyboardButton("Video", callback_data=f"ytm|{msg_id}|video"),
            InlineKeyboardButton("Video + Audio", callback_data=f"ytm|{msg_id}|both"),
        ]])
        # Store pending request for callback handler (shared across users)
        _ytmusic_pending[msg_id] = {"url": url, "title": title, "timestamp": time.time()}
        await update.message.reply_text(
            f"\U0001f3b5 {title}\n\nChoose format:",
            reply_markup=keyboard,
            reply_parameters=reply_params,
        )
        context.user_data["_request_success"] = True
    else:
        success = download_audio(url, f"{base}.mp3")
        if success and os.path.isfile(f"{base}.mp3"):
            with open(f"{base}.mp3", "rb") as f:
                await update.message.reply_audio(
                    audio=f,
                    title=title[:AUDIO_TITLE_MAX],
                    reply_parameters=reply_params,
                )
            _store_download_metadata(context, "audio", f"{base}.mp3")
        else:
            context.user_data["_request_success"] = False
            await update.message.reply_text(
                MSG_DOWNLOAD_FAILED,
                reply_parameters=reply_params,
            )


async def handle_youtube(
    update, context: ContextTypes.DEFAULT_TYPE, url: str,
    base: str, output_path: str, caption: str, reply_params: dict,
) -> bool:
    """Handle regular YouTube URL: download and send video.

    Returns True if video was sent successfully, False otherwise.
    """
    video_ok = await _download_and_send_video(
        url, base, output_path, caption, reply_params, update.message, context
    )
    return video_ok


async def ytmusic_callback(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle YouTube Music format selection callback."""
    query = update.callback_query

    try:
        _, msg_id_str, choice = query.data.split("|")
        msg_id = int(msg_id_str)
    except (ValueError, IndexError):
        await query.answer()
        return

    pending = _ytmusic_pending.pop(msg_id, None)
    if not pending:
        await query.answer(MSG_YTMUSIC_REQUEST_EXPIRED)
        return

    # Check TTL -- reject stale requests
    request_time = pending.get("timestamp")
    if request_time is not None and time.time() - request_time > YTMUSIC_REQUEST_TTL:
        await query.answer(MSG_YTMUSIC_REQUEST_EXPIRED)
        return

    await query.answer()

    url = pending["url"]
    title = pending.get("title", "video")

    # Show typing indicator while downloading
    async with typing_indicator(query.message.chat.id, context.bot):
        # Delete the question message with the keyboard
        try:
            await query.message.delete()
        except Exception:
            pass

        tmp_id, output_path, base = make_video_tmp_path()

        reply_params = {"message_id": msg_id, "allow_sending_without_reply": True}

        try:
            if choice == "audio":
                _log.info("ytmusic_callback: starting audio download for %s", url)
                success = download_audio(url, f"{base}.mp3")
                if success and os.path.isfile(f"{base}.mp3"):
                    with open(f"{base}.mp3", "rb") as f:
                        await update.effective_message.reply_audio(
                            audio=f,
                            title=title[:AUDIO_TITLE_MAX],
                            reply_parameters=reply_params,
                        )
                    _store_download_metadata(context, "audio", f"{base}.mp3")
                    _log.info("ytmusic_callback: audio sent for %s", url)
                else:
                    _log.warning("ytmusic_callback: audio download failed for %s", url)
                    await update.effective_message.reply_text(
                        MSG_YTMUSIC_AUDIO_FAILED,
                        reply_parameters=reply_params,
                    )

            elif choice == "video":
                _log.info("ytmusic_callback: starting video download for %s", url)
                caption = get_caption_for_user(update.effective_message.from_user.id, title)
                video_ok = await _download_and_send_video(
                    url, base, output_path, caption, reply_params, update.effective_message, context
                )
                if video_ok:
                    _log.info("ytmusic_callback: video sent for %s", url)
                else:
                    _log.warning("ytmusic_callback: video download failed for %s", url)
                    await update.effective_message.reply_text(
                        MSG_YTMUSIC_VIDEO_FAILED,
                        reply_parameters=reply_params,
                    )

            elif choice == "both":
                _log.info("ytmusic_callback: starting both download for %s", url)

                # Download video and audio concurrently
                video_task = asyncio.to_thread(download_video, url, output_path, MAX_FILE_SIZE)
                audio_task = asyncio.to_thread(download_audio, url, f"{base}.mp3")
                results = await asyncio.gather(video_task, audio_task, return_exceptions=True)
                video_ok = results[0] is True
                audio_ok = results[1] is True

                for label, result in [("video", results[0]), ("audio", results[1])]:
                    if isinstance(result, Exception):
                        _log.warning("ytmusic_callback: %s download raised exception for %s: %s", label, url, result)

                # Send video first
                if video_ok:
                    downloaded = find_downloaded_file(base)
                    if downloaded:
                        caption = get_caption_for_user(update.effective_message.from_user.id, title)
                        with open(downloaded, "rb") as f:
                            await update.effective_message.reply_video(
                                video=f,
                                caption=caption,
                                reply_parameters=reply_params,
                                supports_streaming=True,
                            )
                        _store_download_metadata(context, "both", downloaded)
                        _log.info("ytmusic_callback: video sent for %s", url)
                    else:
                        await update.effective_message.reply_text(
                            MSG_YTMUSIC_VIDEO_FAILED,
                            reply_parameters=reply_params,
                        )
                else:
                    await update.effective_message.reply_text(
                        MSG_YTMUSIC_VIDEO_FAILED,
                        reply_parameters=reply_params,
                    )

                # Then send audio
                if audio_ok and os.path.isfile(f"{base}.mp3"):
                    with open(f"{base}.mp3", "rb") as f:
                        await update.effective_message.reply_audio(
                            audio=f,
                            title=title[:AUDIO_TITLE_MAX],
                            reply_parameters=reply_params,
                        )
                    if not video_ok:
                        _store_download_metadata(context, "both", f"{base}.mp3")
                    _log.info("ytmusic_callback: audio sent for %s", url)
                else:
                    await update.effective_message.reply_text(
                        MSG_YTMUSIC_AUDIO_FAILED,
                        reply_parameters=reply_params,
                    )

                _log.info("ytmusic_callback: both download completed for %s (video=%s, audio=%s)", url, video_ok, audio_ok)

            else:
                await update.effective_message.reply_text(
                    MSG_YTMUSIC_UNKNOWN_CHOICE,
                    reply_parameters=reply_params,
                )

        except Exception as e:
            await update.effective_message.reply_text(
                f"Error: {e}",
                reply_parameters=reply_params,
            )
        finally:
            cleanup_video_files(base)
            for ext in ["mp3", "m4a"]:
                cleanup_file(f"{base}.{ext}")
