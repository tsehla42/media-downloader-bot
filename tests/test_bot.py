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
