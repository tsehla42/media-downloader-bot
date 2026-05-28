import logging
from logging_config import setup_logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
)

from config import BOT_TOKEN
from handlers import start_command, help_command, handle_url
from inline import inline_query

logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Fetch bot username after application is initialized."""
    me = await application.bot.get_me()
    application.bot_data["bot_username"] = me.username
    logger.info("Bot username: %s", me.username)


def main() -> None:
    """Start the bot."""
    setup_logging()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("Bot started")
    app.run_polling(allowed_updates=["message", "inline_query"])


if __name__ == "__main__":
    main()
