import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers import start_command, help_command, handle_url

@pytest.fixture
def update():
    u = MagicMock()
    u.message = AsyncMock()
    u.message.from_user = MagicMock()
    u.message.from_user.id = 123456
    u.message.text = ""
    u.message.reply_text = AsyncMock()
    u.effective_chat = MagicMock()
    u.effective_chat.id = 123456
    return u

@pytest.fixture
def context():
    return MagicMock()

@pytest.mark.asyncio
async def test_start_command(update, context):
    await start_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Media Downloader Bot" in text

@pytest.mark.asyncio
async def test_help_command(update, context):
    await help_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "YouTube" in text
    assert "TikTok" in text
    assert "Instagram" in text

@pytest.mark.asyncio
async def test_handle_url_replies_downloading(update, context):
    update.message.text = "https://youtube.com/watch?v=abc123"
    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        status_msg = MagicMock()
        status_msg.edit_text = AsyncMock()
        update.message.reply_text = AsyncMock(return_value=status_msg)
        update.message.edit_text = AsyncMock()
        await handle_url(update, context)
        assert update.message.reply_text.called

@pytest.mark.asyncio
async def test_handle_url_rejects_invalid(update, context):
    update.message.text = "not a url"
    await handle_url(update, context)
    # handle_url ignores non-URLs silently (returns early)
    # so reply_text should not be called

@pytest.mark.asyncio
async def test_handle_url_rejects_unknown_platform(update, context):
    update.message.text = "https://example.com/video"
    with patch("handlers.detect_platform", return_value=None):
        await handle_url(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Unsupported" in text
