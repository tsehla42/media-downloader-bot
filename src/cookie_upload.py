"""Admin-only cookie file upload via document messages in P2P chats.

A bot admin sends a .txt document with the caption "cookie update <platform>"
(platform: tt, ig, yt — lowercase only; keyword case-insensitive). The file
is saved as cookies/<platform>-cookie-<date>.txt and copied over the active
cookie path the downloader reads.
"""

import datetime
import logging
import os
import re

from telegram import Update
from telegram.ext import ContextTypes

from auth import is_bot_admin, is_private_chat
from config import COOKIES_DIR, IG_COOKIES_PATH, TIKTOK_COOKIES_PATH, YT_COOKIES_PATH
from logging_config import log_cookie_updated
from messages import (
    MSG_COOKIE_CAPTION_EMPTY,
    MSG_COOKIE_INVALID_CAPTION,
    MSG_COOKIE_INVALID_FILE,
    MSG_COOKIE_UPDATED,
)

_log = logging.getLogger("cookie_upload")

# "cookie update" is case-insensitive; platform must be lowercase tt/ig/yt
_CAPTION_RE = re.compile(r"(?i:cookie update) (tt|ig|yt)")


def _active_path(platform: str) -> str:
    return {
        "tt": TIKTOK_COOKIES_PATH,
        "ig": IG_COOKIES_PATH,
        "yt": YT_COOKIES_PATH,
    }[platform]


def _looks_like_netscape(text: str) -> bool:
    """Check whether text looks like a Netscape cookie file.

    Accepts the standard header line, tab-separated cookie rows (6 fields),
    and #HttpOnly_-prefixed cookie rows.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# Netscape HTTP Cookie File"):
            return True
        if line.startswith("#HttpOnly_") and line.count("\t") >= 5:
            return True
        if not stripped.startswith("#") and line.count("\t") >= 5:
            return True
    return False


async def handle_cookie_document(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle an uploaded cookie file. Silently ignores non-P2P and non-admin."""
    if not is_private_chat(update.effective_chat):
        return

    message = update.message
    sender = message.from_user
    if sender is None or not is_bot_admin(sender.id):
        return

    reply_params = {
        "message_id": message.message_id,
        "allow_sending_without_reply": True,
    }

    caption = (message.caption or "").strip()
    if not caption:
        await message.reply_text(MSG_COOKIE_CAPTION_EMPTY, reply_parameters=reply_params)
        return

    match = _CAPTION_RE.fullmatch(caption)
    if not match:
        await message.reply_text(MSG_COOKIE_INVALID_CAPTION, reply_parameters=reply_params)
        return
    platform = match.group(1)

    document = message.document
    filename = getattr(document, "file_name", "") or ""
    if not filename.lower().endswith(".txt"):
        await message.reply_text(MSG_COOKIE_INVALID_FILE, reply_parameters=reply_params)
        return

    tg_file = await context.bot.get_file(document.file_id)
    data = await tg_file.download_as_bytearray()
    try:
        text = bytes(data).decode("utf-8")
    except UnicodeDecodeError:
        text = ""
    if not _looks_like_netscape(text):
        await message.reply_text(MSG_COOKIE_INVALID_FILE, reply_parameters=reply_params)
        return

    os.makedirs(COOKIES_DIR, exist_ok=True)
    date = datetime.date.today().isoformat()
    dated_path = os.path.join(COOKIES_DIR, f"{platform}-cookie-{date}.txt")
    for path in (dated_path, _active_path(platform)):
        with open(path, "wb") as f:
            f.write(data)

    await message.reply_text(
        MSG_COOKIE_UPDATED.format(platform=platform), reply_parameters=reply_params
    )
    log_cookie_updated(platform, sender, os.path.basename(dated_path))
