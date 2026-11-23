import logging
from logging_config import setup_logging, details_logger, service_logger, log_error

import httpx
from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    Update,
)
from telegram.error import TelegramError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import (
    ALLOWED_GROUP_IDS,
    ALLOWED_IDS_CONFIGURED,
    ALLOWED_USER_IDS,
    BOT_TOKEN,
    GUEST_MODE_ENABLED,
)
from handlers import handle_url, audio_command, my_chat_member_handler
from platforms.youtube import ytmusic_callback
from commands import start_command, help_command, caption_command
from cookie_upload import handle_cookie_document, handle_cookie_reply, cookie_reply_filter
from http_request import MEDIA_WRITE_TIMEOUT, ResilientHTTPXRequest
from messages import MSG_UPLOAD_TIMED_OUT


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to inform the user."""
    from logging_config import is_deleted_reply_error

    if is_deleted_reply_error(context.error):
        # Source message was deleted before the bot replied — user cancelled
        # the request. Silent on purpose (groups + commands not URL-logged).
        details_logger.info(
            "reply target deleted before send — request cancelled: %s", context.error
        )
        return

    log_error(context.error, update)

    if isinstance(update, Update) and update.effective_chat:
        # A stalled upload (WriteTimeout) means the download worked but the send
        # didn't — say so instead of the generic error
        error_text = "An error occurred while processing your request. Please try again later."
        if isinstance(context.error, TimedOut) and isinstance(
            context.error.__cause__, httpx.WriteTimeout
        ):
            error_text = MSG_UPLOAD_TIMED_OUT
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_text,
            )
        except Exception as e:
            details_logger.error("Failed to send error message to user: %s", e)

COMMANDS = [
    BotCommand("start", "Start the bot"),
    BotCommand("help", "Show supported platforms and commands"),
    BotCommand("audio", "Download video as audio (MP3)"),
    BotCommand("caption", "Toggle video captions on/off"),
]


async def _set_commands_safe(bot, commands, scope=None) -> None:
    """setMyCommands that logs and swallows errors so one bad chat
    cannot abort startup registration."""
    try:
        await bot.set_my_commands(commands, scope=scope)
    except TelegramError as e:
        service_logger.warning("Failed to set command scope %s: %s", scope, e)


async def register_command_scopes(bot) -> None:
    """Register the command menu only where it should be visible.

    Allow-all mode: keep the single global menu (no user list to restrict to).
    Allowlist configured: clear the default scope, then register COMMANDS per
    allowed user and per allowed group (all group chats when no group
    allowlist is configured)."""
    if not ALLOWED_IDS_CONFIGURED:
        await _set_commands_safe(bot, COMMANDS)
        return

    await _set_commands_safe(bot, [], scope=BotCommandScopeDefault())
    for user_id in ALLOWED_USER_IDS:
        await _set_commands_safe(bot, COMMANDS, scope=BotCommandScopeChat(user_id))

    if ALLOWED_GROUP_IDS:
        for group_id in ALLOWED_GROUP_IDS:
            await _set_commands_safe(bot, COMMANDS, scope=BotCommandScopeChat(group_id))
    else:
        await _set_commands_safe(bot, COMMANDS, scope=BotCommandScopeAllGroupChats())


async def post_init(application: Application) -> None:
    """Set bot commands, fetch username, start daily cookie expiry check."""
    me = await application.bot.get_me()
    application.bot_data["bot_username"] = me.username
    await register_command_scopes(application.bot)
    service_logger.info("Bot username: @%s", me.username)

    from cookie_expiry import expiry_check_loop
    application.create_task(expiry_check_loop(application.bot))


async def post_shutdown(application: Application) -> None:
    """Log bot shutdown."""
    service_logger.info("Bot stopped")


def main() -> None:
    """Start the bot."""
    setup_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)

    allowed_updates = ["message", "callback_query", "my_chat_member"]
    if GUEST_MODE_ENABLED:
        allowed_updates.append("guest_message")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        # Retry stalled media uploads once; longer write timeout for big files
        .request(ResilientHTTPXRequest(media_write_timeout=MEDIA_WRITE_TIMEOUT))
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Add error handler
    app.add_error_handler(error_handler)

    # Guest mode handler (Bot API 10.0) — must be BEFORE text handler
    # because filters.TEXT now matches guest_message via effective_message
    if GUEST_MODE_ENABLED:
        from guest import handle_guest
        app.add_handler(MessageHandler(filters.UpdateType.GUEST_MESSAGE, handle_guest))

    # Commands and message handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("caption", caption_command))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(CallbackQueryHandler(ytmusic_callback, pattern="^ytm\\|"))
    # Cookie activation reply (`cookie update <platform>` replying to a file)
    # must precede the generic text handler
    app.add_handler(MessageHandler(cookie_reply_filter, handle_cookie_reply))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_cookie_document))
    app.add_handler(ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))

    service_logger.info("Bot started")

    app.run_polling(
        allowed_updates=allowed_updates,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
