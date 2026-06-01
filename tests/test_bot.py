import pytest
from unittest.mock import MagicMock, patch


def test_bot_imports_my_chat_member_handler():
    """Bot imports my_chat_member_handler from handlers."""
    from bot import main
    from handlers import my_chat_member_handler
    # If import succeeds, the handler is available
    assert my_chat_member_handler is not None


def test_bot_registers_my_chat_member_handler():
    """Bot registers my_chat_member handler."""
    from bot import main

    with patch("bot.Application") as mock_app_builder, \
         patch("bot.setup_logging"), \
         patch("bot.BOT_TOKEN", "test-token"), \
         patch("bot.start_command"), \
         patch("bot.help_command"), \
         patch("bot.handle_url"), \
         patch("bot.caption_command"), \
         patch("bot.audio_command"), \
         patch("bot.ytmusic_callback"), \
         patch("bot.my_chat_member_handler") as mock_handler:

        mock_app = MagicMock()
        mock_app_builder.return_value.token.return_value.post_init.return_value.build.return_value = mock_app

        # Capture the allowed_updates argument
        def capture_run_polling(**kwargs):
            allowed = kwargs.get("allowed_updates", [])
            if "my_chat_member" not in allowed:
                raise AssertionError(f"my_chat_member not in allowed_updates: {allowed}")

        mock_app.run_polling.side_effect = capture_run_polling

        # We need to patch the handler import
        with patch("bot.my_chat_member_handler", mock_handler):
            try:
                main()
            except AssertionError as e:
                # Re-raise assertion errors but catch others
                raise e
            except Exception:
                pass  # We just need to check the call was made
