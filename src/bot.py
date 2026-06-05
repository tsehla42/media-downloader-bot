import logging
from logging_config import setup_logging, details_logger, service_logger

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN
from handlers import handle_url, audio_command, my_chat_member_handler
from platforms.youtube import ytmusic_callback
from commands import start_command, help_command, caption_command


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to inform the user."""
    details_logger.error("Exception while handling an update:", exc_info=context.error)

    # Send a message to the user if possible
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An error occurred while processing your request. Please try again later.",
            )
        except Exception as e:
            details_logger.error("Failed to send error message to user: %s", e)

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
    service_logger.info("Bot username: @%s", me.username)


async def post_shutdown(application: Application) -> None:
    """Log bot shutdown."""
    service_logger.info("Bot stopped")


def main() -> None:
    """Start the bot."""
    setup_logging()
    # Suppress noisy httpx request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Add error handler
    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("caption", caption_command))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(CallbackQueryHandler(ytmusic_callback, pattern="^ytm\\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, my_chat_member_handler))

    service_logger.info("Bot started")
    app.run_polling(
        allowed_updates=["message", "callback_query", "my_chat_member"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
