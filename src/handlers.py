import os
import uuid
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from config import DOWNLOAD_DIR, MAX_FILE_SIZE, ALLOWED_USER_IDS
from utils import detect_platform, is_valid_url, extract_urls, cleanup_file
from downloader import get_metadata, download_video, download_audio, download_images
from logging_config import log_request, log_error


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
        "Send me a YouTube, TikTok, or Instagram URL and I'll download it for you.\n\n"
        "Commands:\n"
        "/help - Show supported platforms\n"
        "/audio <url> - Download as audio (MP3)\n\n"
        f"You can also use inline mode: @{bot_username} <url>"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    bot_username = context.bot_data.get("bot_username", "botname")
    await update.message.reply_text(
        "Supported platforms:\n"
        "- YouTube (videos, shorts)\n"
        "- TikTok (videos, no watermark)\n"
        "- Instagram (reels, posts, carousels)\n\n"
        "Usage:\n"
        "1. Send a URL directly\n"
        "2. Use /audio <url> for audio extraction\n"
        f"3. Use inline mode: @{bot_username} <url>"
    )


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /audio command - download as MP3."""
    if not _is_allowed(update.message.from_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    text = update.message.text.replace("/audio", "").strip()
    if not text:
        await update.message.reply_text("Usage: /audio <url>")
        return

    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text("Please provide a valid URL.")
        return

    url = urls[0]
    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text(
            "Unsupported platform. Use /help to see supported sites."
        )
        return

    status_msg = await update.message.reply_text("Downloading audio...")

    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.mp3")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        success = download_audio(url, output_path)
        if success and os.path.isfile(output_path):
            with open(output_path, "rb") as f:
                await update.message.reply_audio(audio=f)
            await status_msg.edit_text("Audio sent!")
        else:
            await status_msg.edit_text("Failed to download audio. Check the URL and try again.")
    except Exception as e:
        await status_msg.edit_text(f"Error: {e}")
    finally:
        cleanup_file(output_path)


async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle messages containing URLs."""
    if not update.message or not update.message.text:
        return

    if not _is_allowed(update.message.from_user.id):
        return

    text = update.message.text.strip()

    if text.startswith("/audio"):
        await audio_command(update, context)
        return

    if not is_valid_url(text):
        return

    urls = extract_urls(text)
    if not urls:
        await update.message.reply_text("Please send a valid URL.")
        return

    url = urls[0]
    platform = detect_platform(url)
    if not platform:
        await update.message.reply_text(
            "Unsupported platform. I support YouTube, TikTok, and Instagram."
        )
        return

    status_msg = await update.message.reply_text("Fetching info...")
    metadata = get_metadata(url)
    if not metadata:
        await status_msg.edit_text(
            "Could not fetch video info. The content may be private or the URL invalid."
        )
        return

    title = metadata.get("title", "video")
    await status_msg.edit_text(f"Downloading: {title[:50]}...")

    tmp_id = uuid.uuid4().hex[:8]
    output_path = os.path.join(DOWNLOAD_DIR, f"{tmp_id}.%(ext)s")
    base = os.path.join(DOWNLOAD_DIR, tmp_id)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    try:
        if platform == "instagram" and metadata.get("extractor") == "instagram":
            images = download_images(url, os.path.join(DOWNLOAD_DIR, tmp_id))
            if images:
                for i in range(0, len(images), 10):
                    batch = images[i:i+10]
                    media = [InputMediaPhoto(open(img, "rb")) for img in batch]
                    await update.message.reply_media_group(media=media)
                    for img in batch:
                        os.remove(img)
                await status_msg.edit_text("Images sent!")
                return

        success = download_video(url, output_path, MAX_FILE_SIZE, platform=platform)
        if not success:
            await status_msg.edit_text("Download failed. Try again later.")
            return

        downloaded = None
        for ext in ["mp4", "webm", "mkv", "mp3", "m4a"]:
            candidate = f"{base}.{ext}"
            if os.path.isfile(candidate):
                downloaded = candidate
                break

        if not downloaded:
            await status_msg.edit_text("Download failed. File not found.")
            return

        with open(downloaded, "rb") as f:
            await update.message.reply_video(video=f, caption=title[:1024])

        log_request(
            url=url,
            platform=platform,
            content_type="video",
            user=update.message.from_user,
            chat=update.message.chat,
            media_info={
                "duration_seconds": metadata.get("duration") if metadata else None,
                "file_size_mb": round(os.path.getsize(downloaded) / (1024 * 1024), 2) if downloaded else 0,
                "image_count": None,
                "quality": metadata.get("format") if metadata else None,
            },
        )
    except Exception as e:
        log_error(
            url=url,
            error=str(e),
            platform=platform,
            user=update.message.from_user,
            chat=update.message.chat,
        )
        await status_msg.edit_text(f"Error: {e}")
    finally:
        for ext in ["mp4", "webm", "mkv", "mp3", "m4a"]:
            cleanup_file(f"{base}.{ext}")
