"""Authorization checks for the bot."""

from telegram import Update

from config import ALLOWED_USER_IDS, ALLOWED_GROUP_IDS, BOT_ADMIN_IDS, ALLOWED_IDS_CONFIGURED

_already_told_users: set[int] = set()


def is_bot_admin(user_id: int) -> bool:
    """Check if user is a bot admin. Empty allowlist = allow all."""
    if not BOT_ADMIN_IDS:
        return True
    return user_id in BOT_ADMIN_IDS


def was_notified(user_id: int) -> bool:
    """Check if user has already been told they're not authorized."""
    return user_id in _already_told_users


def mark_notified(user_id: int) -> None:
    """Mark user as having been notified about unauthorized access."""
    _already_told_users.add(user_id)


def is_group_chat(update: Update) -> bool:
    """Check if the update is from a group chat."""
    chat = update.effective_chat
    return chat.type in ("group", "supergroup")


def _is_allowed(user_id: int) -> bool:
    """Check if user is in the allowlist.

    If no ID sources configured (no JSON file, no env var) = allow all.
    If ID sources configured but user not in list = deny.
    """
    if not ALLOWED_IDS_CONFIGURED:
        return True
    return user_id in ALLOWED_USER_IDS


def _is_allowed_group(chat_id: int) -> bool:
    """Check if group is in the allowlist. Empty allowlist = allow all."""
    if not ALLOWED_GROUP_IDS:
        return True
    return chat_id in ALLOWED_GROUP_IDS


def is_authorized(update: Update) -> bool:
    """Check if request is authorized.
    Groups: always allowed (bot only exists if admin added it).
    DMs: checked against ALLOWED_USER_IDS (empty = allow all).
    """
    if is_group_chat(update):
        return True  # Groups: bot only exists if admin added it
    if update.message and update.message.from_user:
        return _is_allowed(update.message.from_user.id)
    return False
