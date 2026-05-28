import logging
from logging_config import setup_logging
from telegram import BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    filters,
)

from config import BOT_TOKEN
from handlers import start_command, help_command, handle_url, caption_command
from inline import inline_query

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show supported platforms and commands"),
    BotCommand("audio", "Download video as audio (MP3)"),
    BotCommand("caption", "Toggle video captions on/off"),
]


async def post_init(application: Application) -> None:
    """Set bot commands and fetch username after initialization."""
    me = await application.bot.get_me()
    application.bot_data["bot_username"] = me.username
    await application.bot.set_my_commands(COMMANDS)
    logger.info("Bot username: @%s", me.username)


def main() -> None:
    """Start the bot."""
    setup_logging()
    # Suppress noisy httpx request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("caption", caption_command))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("Bot started")
    app.run_polling(allowed_updates=["message", "inline_query"])


if __name__ == "__main__":
    main()
