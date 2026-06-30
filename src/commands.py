# src/commands.py
"""User-facing commands that don't perform downloads."""

from telegram import Update
from telegram.ext import ContextTypes

from config import MAX_FILE_SIZE
from auth import is_authorized, was_notified, mark_notified
from logging_config import log_unauthorized_access
from messages import (
    MSG_UNAUTHORIZED, MSG_CAPTION_ENABLED, MSG_CAPTION_DISABLED,
    MSG_CAPTION_STATUS, MSG_START, MSG_HELP,
)


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
        user_id = update.message.from_user.id
        if not was_notified(user_id):
            await update.message.reply_text(MSG_UNAUTHORIZED)
            mark_notified(user_id)
            log_unauthorized_access(update.message.from_user, update.message.chat, "/start")
        return

    await update.message.reply_text(
        MSG_START.format(max_file_size=MAX_FILE_SIZE)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    if not is_authorized(update):
        user_id = update.message.from_user.id
        if not was_notified(user_id):
            await update.message.reply_text(MSG_UNAUTHORIZED)
            mark_notified(user_id)
            log_unauthorized_access(update.message.from_user, update.message.chat, "/help")
        return

    await update.message.reply_text(
        MSG_HELP.format(max_file_size=MAX_FILE_SIZE)
    )


async def caption_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /caption command to toggle caption preferences."""
    if not is_authorized(update):
        user_id = update.message.from_user.id
        if not was_notified(user_id):
            await update.message.reply_text(
                MSG_UNAUTHORIZED,
                reply_parameters={"message_id": update.message.message_id},
            )
            mark_notified(user_id)
            log_unauthorized_access(update.message.from_user, update.message.chat, "/caption")
        return

    text = update.message.text.replace("/caption", "").strip().lower()
    user_id = update.message.from_user.id

    if text in ("on", "1", "true", "yes"):
        _user_caption_prefs[user_id] = False
        await update.message.reply_text(
            MSG_CAPTION_ENABLED,
            reply_parameters={"message_id": update.message.message_id},
        )
    elif text in ("off", "0", "false", "no"):
        _user_caption_prefs[user_id] = True
        await update.message.reply_text(
            MSG_CAPTION_DISABLED,
            reply_parameters={"message_id": update.message.message_id},
        )
    else:
        current = _user_caption_prefs.get(user_id, True)
        state = "OFF (no captions)" if current else "ON (captions shown)"
        await update.message.reply_text(
            MSG_CAPTION_STATUS.format(state=state),
            reply_parameters={"message_id": update.message.message_id},
        )
