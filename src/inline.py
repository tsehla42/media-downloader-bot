import uuid
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

from config import ALLOWED_USER_IDS
from utils import detect_platform, extract_urls
from downloader import get_metadata


def _is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries like @botname <url>."""
    query = update.inline_query
    if not _is_allowed(query.from_user.id):
        await query.answer(results=[], cache_time=0)
        return

    text = query.query.strip()
    if not text:
        await query.answer(results=[], cache_time=0)
        return

    urls = extract_urls(text)
    if not urls:
        await query.answer(results=[], cache_time=0)
        return

    url = urls[0]
    platform = detect_platform(url)
    if not platform:
        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="Unsupported platform",
                input_message_content=InputTextMessageContent(
                    message_text=f"Unsupported platform for: {url}"
                ),
            )
        ]
        await query.answer(results=results, cache_time=0)
        return

    metadata = get_metadata(url)
    if not metadata:
        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title="Could not fetch info",
                input_message_content=InputTextMessageContent(
                    message_text=f"Failed to fetch info for: {url}"
                ),
            )
        ]
    else:
        title = metadata.get("title", "Media")
        thumbnail = metadata.get("thumbnail", "")
        results = [
            InlineQueryResultArticle(
                id=uuid.uuid4().hex,
                title=title[:100],
                description=f"Download from {platform}",
                thumbnail_url=thumbnail if thumbnail else None,
                input_message_content=InputTextMessageContent(
                    message_text=url
                ),
            )
        ]

    await query.answer(results=results, cache_time=300)
