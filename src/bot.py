import logging
from logging_config import setup_logging
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN
from handlers import start_command, help_command, handle_url, caption_command

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to inform the user."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    # Send a message to the user if possible
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An error occurred while processing your request. Please try again later.",
            )
        except Exception as e:
            logger.error("Failed to send error message to user: %s", e)

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

    # Add error handler
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("caption", caption_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("Bot started")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
