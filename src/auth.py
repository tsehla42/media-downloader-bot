"""Authorization checks for the bot."""

from telegram import Update

from config import ALLOWED_USER_IDS, ALLOWED_GROUP_IDS


def is_group_chat(update: Update) -> bool:
    """Check if the update is from a group chat."""
    chat = update.effective_chat
    return chat.type in ("group", "supergroup")


def _is_allowed(user_id: int) -> bool:
    """Check if user is in the allowlist. Empty allowlist = allow all."""
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


def _is_allowed_group(chat_id: int) -> bool:
    """Check if group is in the allowlist. Empty allowlist = allow all."""
    if not ALLOWED_GROUP_IDS:
        return True
    return chat_id in ALLOWED_GROUP_IDS


def is_authorized(update: Update) -> bool:
    """Check if request is authorized. Groups checked against ALLOWED_GROUP_IDS (empty = allow all), DMs checked against ALLOWED_USER_IDS (empty = allow all)."""
    if is_group_chat(update):
        return _is_allowed_group(update.effective_chat.id)
    if update.message and update.message.from_user:
        return _is_allowed(update.message.from_user.id)
    return False
