import pytest
from unittest.mock import MagicMock, patch


def test_bot_imports_my_chat_member_handler():
    """Bot imports my_chat_member_handler from handlers."""
    from bot import main
    from handlers import my_chat_member_handler
    # If import succeeds, the handler is available
    assert my_chat_member_handler is not None


def test_bot_registers_my_chat_member_handler():
    """Bot registers my_chat_member handler with ChatMemberHandler."""
    from bot import main

    with patch("bot.Application") as mock_app_builder, \
         patch("bot.setup_logging"), \
         patch("bot.BOT_TOKEN", "test-token"), \
         patch("bot.GUEST_MODE_ENABLED", False), \
         patch("bot.start_command"), \
         patch("bot.help_command"), \
         patch("bot.handle_url"), \
         patch("bot.caption_command"), \
         patch("bot.audio_command"), \
         patch("bot.ytmusic_callback"), \
         patch("bot.ChatMemberHandler") as mock_chat_member_handler, \
         patch("bot.my_chat_member_handler") as mock_handler:

        mock_chat_member_handler.return_value = mock_handler
        mock_app = MagicMock()
        mock_app_builder.builder.return_value.token.return_value.post_init.return_value.post_shutdown.return_value.build.return_value = mock_app

        main()

        # Verify ChatMemberHandler was used (not MessageHandler)
        mock_chat_member_handler.assert_called_once()
        call_args = mock_chat_member_handler.call_args
        assert call_args[0][0] is mock_handler
        # Verify it was registered with add_handler
        mock_app.add_handler.assert_any_call(mock_handler)


def test_error_handler_silent_on_deleted_reply():
    """If the source message was deleted before the bot replied, no user-facing
    error message is sent and no unhandled-exception log is written."""
    from unittest.mock import AsyncMock
    from telegram.error import BadRequest
    from bot import error_handler

    context = MagicMock()
    context.error = BadRequest("Bad Request: message to be replied not found")
    context.bot.send_message = AsyncMock()

    with patch("bot.log_error") as mock_log_error, \
         patch("bot.details_logger"):
        import asyncio
        asyncio.run(error_handler(MagicMock(), context))

    mock_log_error.assert_not_called()
    context.bot.send_message.assert_not_called()


def test_error_handler_still_reports_other_errors():
    from unittest.mock import AsyncMock
    from bot import error_handler

    context = MagicMock()
    context.error = RuntimeError("boom")
    context.bot.send_message = AsyncMock()

    with patch("bot.log_error") as mock_log_error:
        import asyncio
        asyncio.run(error_handler(MagicMock(), context))

    mock_log_error.assert_called_once()


def test_bot_registers_cookie_reply_handler_before_text_handler():
    """`cookie update <platform>` replies to an uploaded file must reach
    handle_cookie_reply, and that handler must be registered BEFORE the
    generic text handler so handle_url doesn't consume the update."""
    from bot import main

    with patch("bot.Application") as mock_app_builder, \
         patch("bot.setup_logging"), \
         patch("bot.BOT_TOKEN", "test-token"), \
         patch("bot.GUEST_MODE_ENABLED", False), \
         patch("bot.start_command"), \
         patch("bot.help_command"), \
         patch("bot.caption_command"), \
         patch("bot.audio_command"), \
         patch("bot.ytmusic_callback"), \
         patch("bot.handle_cookie_document") as mock_doc, \
         patch("bot.handle_cookie_reply") as mock_reply, \
         patch("bot.handle_url") as mock_url, \
         patch("bot.MessageHandler") as mock_msg_handler, \
         patch("bot.ChatMemberHandler"):
        instances = []

        def _make_handler(*args, **kwargs):
            inst = MagicMock(name="MessageHandlerInstance")
            inst.registered_args = args
            instances.append(inst)
            return inst

        mock_msg_handler.side_effect = _make_handler

        mock_app = MagicMock()
        mock_app_builder.builder.return_value.token.return_value.post_init.return_value.post_shutdown.return_value.build.return_value = mock_app

        main()

        callbacks = [h.registered_args[1] for h in instances]
        assert mock_reply in callbacks, "cookie reply handler not registered"
        assert mock_url in callbacks, "text handler not registered"

        cookie_inst = instances[callbacks.index(mock_reply)]
        url_inst = instances[callbacks.index(mock_url)]
        added = [c[0][0] for c in mock_app.add_handler.call_args_list]
        assert cookie_inst in added, "cookie reply handler not added to app"
        assert url_inst in added, "text handler not added to app"
        assert instances.index(cookie_inst) < instances.index(url_inst), \
            "cookie reply handler must be registered before handle_url"
