import asyncio
import os
import uuid
from telegram import Update, InputMediaPhoto
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import DOWNLOAD_DIR, MAX_FILE_SIZE, ALLOWED_USER_IDS
from utils import detect_platform, is_valid_url, extract_urls, cleanup_file
from downloader import get_metadata, download_video, download_audio, download_images
from logging_config import log_error, with_request_logging


async def _start_typing(chat_id: int, bot) -> asyncio.Task:
    """Start a loop that sends typing action every 4 seconds. Returns a task to cancel."""
    # Send first typing action immediately so indicator appears right away
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    async def _loop():
        try:
            while True:
                await asyncio.sleep(4)
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except asyncio.CancelledError:
            pass
    return asyncio.create_task(_loop())


# Per-user caption preferences: user_id -> bool (True = remove caption)
_user_caption_prefs: dict[int, bool] = {}


def _is_allowed(user_id: int) -> bool:
    """Check if user is in allowlist (empty list = allow all)."""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    bot_username = context.bot_data.get("bot_username", "botname")
    await update.message.reply_text(
        "Media Downloader Bot\n\n"
        "Send me a YouTube, TikTok, or Instagram URL and I'll download it for you.\n"
        "You can send multiple URLs in one message or send them one by one.\n"
        f"Max file size: {MAX_FILE_SIZE}MB\n\n"
        "Commands:\n"
        "/help - Show supported platforms and commands\n"
        "/audio <url> - Download as audio (MP3)\n"
        "/caption on|off - Toggle video captions\n\n"
        f"Inline mode: @{bot_username} <url>"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    bot_username = context.bot_data.get("bot_username", "botname")
    await update.message.reply_text(
        "Supported platforms:\n"
        "- YouTube (videos, shorts)\n"
        "- TikTok (videos, no watermark)\n"
        "- Instagram (reels, posts, carousels)\n\n"
        "Commands:\n"
        "/audio <url> - Download as audio (MP3)\n"
        "/caption on - Show video captions\n"
        "/caption off - Remove video captions (default)\n\n"
        f"Max file size: {MAX_FILE_SIZE}MB\n"
        "You can send multiple URLs in one message.\n\n"
        f"Inline mode: @{bot_username} <url>"
    )


async def caption_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /caption command - toggle video caption on/off."""
    if not _is_allowed(update.message.from_user.id):
        return

    text = update.message.text.replace("/caption", "").strip().lower()
    user_id = update.message.from_user.id

    if text in ("on", "1", "true", "yes"):
        _user_caption_prefs[user_id] = False
        await update.message.reply_text(
            "Captions enabled. Videos will include the title.",
            reply_parameters={"message_id": update.message.message_id},
        )
    elif text in ("off", "0", "false", "no"):
        _user_caption_prefs[user_id] = True
        await update.message.reply_text(
            "Captions removed. Videos will be sent without description.",
            reply_parameters={"message_id": update.message.message_id},
        )
    else:
        current = _user_caption_prefs.get(user_id, True)
        state = "OFF (no captions)" if current else "ON (captions shown)"
        await update.message.reply_text(
            f"Current caption setting: {state}\n\n"
            "Usage:\n"
            "/caption on - Show video captions\n"
            "/caption off - Remove video captions (default)",
            reply_parameters={"message_id": update.message.message_id},
        )


@with_request_logging
async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /audio command - download as MP3."""
    reply_params = {"message_id": update.message.message_id}

    if not _is_allowed(update.message.from_user.id):
        await update.message.reply_text(
            "You are not authorized to use this bot.",
            reply_parameters=reply_params,
        )
        return

    text = update.message.text.replace("/audio", "").strip()
    if not text:
        await update.message.reply_text(
            "Usage: /audio <url>",
            reply_parameters=reply_params,
        )
        return

    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text(
            "Please provide a valid URL.",
            reply_parameters=reply_params,
        )
        return

    url = urls[0]
    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text(
            "Unsupported platform. Use /help to see supported sites.",
            reply_parameters=reply_params,
        )
        return

    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.mp3")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        success = download_audio(url, output_path)
        if success and os.path.isfile(output_path):
            with open(output_path, "rb") as f:
                await update.message.reply_audio(
                    audio=f,
                    reply_parameters=reply_params,
                )
        else:
            await update.message.reply_text(
                "Failed to download audio. Check the URL and try again.",
                reply_parameters=reply_params,
            )
    except Exception as e:
        await update.message.reply_text(
            f"Error: {e}",
            reply_parameters=reply_params,
        )
    finally:
        cleanup_file(output_path)


async def _download_and_send(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    """Download and send a single URL."""
    reply_params = {"message_id": update.message.message_id}
    base = None
    platform = None

    try:
        platform = detect_platform(url)
        if not platform:
            await update.message.reply_text(
                "Unsupported platform. I support YouTube, TikTok, and Instagram.",
                reply_parameters=reply_params,
            )
            return

        metadata = get_metadata(url)
        if not metadata:
            await update.message.reply_text(
                "Could not fetch video info. The content may be private or the URL invalid.",
                reply_parameters=reply_params,
            )
            return

        title = metadata.get("title", "video")

        tmp_id = uuid.uuid4().hex[:8]
        output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
        base = os.path.join(DOWNLOAD_DIR, tmp_id)
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        if platform == "instagram" and metadata.get("extractor") == "instagram":
            images = download_images(url, os.path.join(DOWNLOAD_DIR, tmp_id))
            if images:
                for i in range(0, len(images), 10):
                    batch = images[i:i+10]
                    media = [InputMediaPhoto(open(img, "rb")) for img in batch]
                    await update.message.reply_media_group(
                        media=media,
                        reply_parameters=reply_params,
                    )
                    for img in batch:
                        os.remove(img)
                return

        success = download_video(url, output_path, MAX_FILE_SIZE, platform=platform)
        if not success:
            await update.message.reply_text(
                "Download failed. Try again later.",
                reply_parameters=reply_params,
            )
            return

        downloaded = None
        for ext in ["mp4", "webm", "mkv", "mp3", "m4a"]:
            candidate = f"{base}.{ext}"
            if os.path.isfile(candidate):
                downloaded = candidate
                break

        if not downloaded:
            await update.message.reply_text(
                "Download failed. File not found.",
                reply_parameters=reply_params,
            )
            return

        with open(downloaded, "rb") as f:
            await update.message.reply_video(
                video=f,
                caption="" if _user_caption_prefs.get(update.message.from_user.id, True) else title[:1024],
                reply_parameters=reply_params,
            )
    except Exception as e:
        log_error(
            url=url,
            error=str(e),
            platform=platform,
            user=update.message.from_user,
            chat=update.message.chat,
        )
        await update.message.reply_text(
            f"Error: {e}",
            reply_parameters=reply_params,
        )
    finally:
        if base:
            for ext in ["mp4", "webm", "mkv", "mp3", "m4a"]:
                cleanup_file(f"{base}.{ext}")


@with_request_logging
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing URLs."""
    if not update.message or not update.message.text:
        return

    if not _is_allowed(update.message.from_user.id):
        return

    typing_task = await _start_typing(update.message.chat.id, context.bot)
    try:
        text = update.message.text.strip()

        if text.startswith("/audio"):
            await audio_command(update, context)
            return

        if not is_valid_url(text):
            return

        urls = extract_urls(text)
        if not urls:
            await update.message.reply_text(
                "Please send a valid URL.",
                reply_parameters={"message_id": update.message.message_id},
            )
            return

        for url in urls:
            await _download_and_send(update, context, url)
    finally:
        typing_task.cancel()
