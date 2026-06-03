# src/commands.py
"""User-facing commands that don't perform downloads."""

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from auth import is_authorized
from logging_config import log_new_user, is_new_user


# Per-user caption preferences: user_id -> bool (True = remove caption)
_user_caption_prefs: dict[int, bool] = {}


def get_caption_for_user(user_id: int, title: str) -> str:
    """Get caption string based on user preference. Returns empty string if captions disabled."""
    if _user_caption_prefs.get(user_id, True):
        return ""
    return title[:1024]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    if not is_authorized(update):
        await update.message.reply_text("You are not authorized to use this bot")
        return

    user = update.message.from_user
    if is_new_user(user.id):
        log_new_user(user)

    await update.message.reply_text(
        "Media Downloader Bot\n\n"
        "Send me a YouTube, TikTok, or Instagram URL and I'll download it for you\n"
        "You can send multiple URLs in one message or send them one by one.\n"
        f"Max file size: {MAX_FILE_SIZE}MB\n\n"
        "Commands:\n"
        "/help - Show supported platforms and commands\n"
        "/audio <url> - Download as audio (MP3)\n"
        "/caption on|off - Toggle video captions"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_authorized(update):
        await update.message.reply_text("You are not authorized to use this bot")
        return

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
        "You can send multiple URLs in one message."
    )


async def caption_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /caption command to toggle caption preferences."""
    if not is_authorized(update):
        await update.message.reply_text(
            "You are not authorized to use this bot",
            reply_parameters={"message_id": update.message.message_id},
        )
        return

    text = update.message.text.replace("/caption", "").strip().lower()
    user_id = update.message.from_user.id

    if text in ("on", "1", "true", "yes"):
        _user_caption_prefs[user_id] = False
        await update.message.reply_text(
            "Captions enabled. Videos will include the title",
            reply_parameters={"message_id": update.message.message_id},
        )
    elif text in ("off", "0", "false", "no"):
        _user_caption_prefs[user_id] = True
        await update.message.reply_text(
            "Captions removed. Videos will be sent without description",
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
