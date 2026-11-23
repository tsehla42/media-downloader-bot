import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
        mock_app_builder.builder.return_value.token.return_value.request.return_value.post_init.return_value.post_shutdown.return_value.build.return_value = mock_app

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
        mock_app_builder.builder.return_value.token.return_value.request.return_value.post_init.return_value.post_shutdown.return_value.build.return_value = mock_app

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


def test_bot_configures_resilient_request_with_media_timeout():
    """main() wires a ResilientHTTPXRequest with a bumped media write timeout
    (120s vs PTB's 20s default) so large uploads tolerate slow uplinks, and
    retries kick in only after that."""
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
         patch("bot.ChatMemberHandler"), \
         patch("bot.my_chat_member_handler"), \
         patch("bot.ResilientHTTPXRequest") as mock_req_cls:
        mock_app = MagicMock()
        builder = mock_app_builder.builder.return_value
        builder.token.return_value.request.return_value.post_init.return_value \
            .post_shutdown.return_value.build.return_value = mock_app

        main()

        mock_req_cls.assert_called_once_with(media_write_timeout=120.0)
        builder.token.return_value.request.assert_called_once_with(
            mock_req_cls.return_value
        )


def test_error_handler_explains_stalled_upload():
    """A TimedOut caused by httpx.WriteTimeout (upload stalled after the download
    succeeded) gets a specific message, not the generic error text."""
    import asyncio
    import httpx
    from unittest.mock import AsyncMock
    from telegram import Update
    from telegram.error import TimedOut
    from bot import error_handler
    from messages import MSG_UPLOAD_TIMED_OUT

    context = MagicMock()
    err = TimedOut()
    err.__cause__ = httpx.WriteTimeout("write stalled")
    context.error = err
    context.bot.send_message = AsyncMock()

    update = Update(update_id=1, message=MagicMock())
    with patch("bot.log_error"), patch("bot.details_logger"):
        asyncio.run(error_handler(update, context))

    sent = context.bot.send_message.call_args.kwargs["text"]
    assert sent == MSG_UPLOAD_TIMED_OUT, (
        f"expected upload-timeout message, got: {sent!r}"
    )


@pytest.mark.asyncio
async def test_allowlist_mode_clears_global_and_registers_per_user():
    """With an allowlist configured, the global (default-scope) menu is cleared
    first, then COMMANDS is registered per allowed user chat."""
    from telegram import BotCommandScopeChat, BotCommandScopeDefault
    from bot import COMMANDS, register_command_scopes

    bot = AsyncMock()
    with patch("bot.ALLOWED_IDS_CONFIGURED", True), \
         patch("bot.ALLOWED_USER_IDS", {111, 222}), \
         patch("bot.ALLOWED_GROUP_IDS", []):
        await register_command_scopes(bot)

    calls = bot.set_my_commands.call_args_list
    assert calls[0].args == ([],)  # first call clears the default scope
    assert isinstance(calls[0].kwargs["scope"], BotCommandScopeDefault)
    per_user = {
        c.kwargs["scope"].chat_id for c in calls
        if isinstance(c.kwargs["scope"], BotCommandScopeChat)
    }
    assert per_user == {111, 222}
    default_clears = [
        c for c in calls if isinstance(c.kwargs["scope"], BotCommandScopeDefault)
    ]
    assert len(default_clears) == 1  # global menu cleared exactly once
    for c in calls[1:]:  # every registration after the clear carries COMMANDS
        assert c.args == (COMMANDS,)


@pytest.mark.asyncio
async def test_allowall_mode_keeps_single_global_menu():
    """No allowlist configured (allow-all): one global registration, no
    default-scope clearing, no per-chat calls."""
    from bot import COMMANDS, register_command_scopes

    bot = AsyncMock()
    with patch("bot.ALLOWED_IDS_CONFIGURED", False):
        await register_command_scopes(bot)

    bot.set_my_commands.assert_called_once()
    c = bot.set_my_commands.call_args
    assert c.args == (COMMANDS,)
    assert c.kwargs.get("scope") is None


@pytest.mark.asyncio
async def test_configured_groups_registered_individually():
    """Each allowed group chat gets the menu via BotCommandScopeChat."""
    from telegram import BotCommandScopeChat
    from bot import register_command_scopes

    bot = AsyncMock()
    with patch("bot.ALLOWED_IDS_CONFIGURED", True), \
         patch("bot.ALLOWED_USER_IDS", set()), \
         patch("bot.ALLOWED_GROUP_IDS", [-1001, -1002]):
        await register_command_scopes(bot)

    group_scopes = {
        c.kwargs["scope"].chat_id for c in bot.set_my_commands.call_args_list
        if isinstance(c.kwargs["scope"], BotCommandScopeChat)
        and c.kwargs["scope"].chat_id < 0
    }
    assert group_scopes == {-1001, -1002}


@pytest.mark.asyncio
async def test_empty_group_allowlist_registers_all_group_chats():
    """Empty ALLOWED_GROUP_IDS (= all groups allowed) registers one
    BotCommandScopeAllGroupChats call, never skips groups."""
    from telegram import BotCommandScopeAllGroupChats, BotCommandScopeChat
    from bot import register_command_scopes

    bot = AsyncMock()
    with patch("bot.ALLOWED_IDS_CONFIGURED", True), \
         patch("bot.ALLOWED_USER_IDS", set()), \
         patch("bot.ALLOWED_GROUP_IDS", []):
        await register_command_scopes(bot)

    scopes = [c.kwargs["scope"] for c in bot.set_my_commands.call_args_list]
    assert any(isinstance(s, BotCommandScopeAllGroupChats) for s in scopes)
    assert not any(isinstance(s, BotCommandScopeChat) for s in scopes)


@pytest.mark.asyncio
async def test_scope_failure_does_not_abort_registration():
    """A TelegramError from any setMyCommands call is logged and swallowed;
    every remaining scope still gets registered."""
    from telegram.error import TelegramError
    from bot import register_command_scopes

    bot = AsyncMock()
    bot.set_my_commands = AsyncMock(
        side_effect=[TelegramError("boom"), True, True]
    )
    with patch("bot.ALLOWED_IDS_CONFIGURED", True), \
         patch("bot.ALLOWED_USER_IDS", {111}), \
         patch("bot.ALLOWED_GROUP_IDS", [-1001]), \
         patch("bot.service_logger") as mock_log:
        await register_command_scopes(bot)  # must not raise

    assert bot.set_my_commands.call_count == 3
    mock_log.warning.assert_called_once()


@pytest.mark.asyncio
async def test_post_init_registers_scoped_commands():
    """post_init delegates command registration to register_command_scopes
    and keeps its other duties (bot_data username, cookie expiry loop)."""
    from bot import post_init

    app = MagicMock()
    app.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    app.bot.set_my_commands = AsyncMock()
    app.bot_data = {}  # plain dict: MagicMock __getitem__/__setitem__ don't persist
    app.create_task = MagicMock()

    with patch("bot.register_command_scopes", new=AsyncMock()) as mock_reg, \
         patch("bot.service_logger") as mock_log:
        await post_init(app)

    mock_reg.assert_awaited_once_with(app.bot)
    app.bot.set_my_commands.assert_not_called()
    assert app.bot_data["bot_username"] == "testbot"
    mock_log.info.assert_called_once_with("Bot username: @%s", "testbot")
    app.create_task.assert_called_once()
    coro = app.create_task.call_args[0][0]
    coro.close()  # never awaited in test — close to avoid warnings
