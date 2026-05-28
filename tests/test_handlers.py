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


import os


@pytest.mark.asyncio
async def test_handle_url_logs_request():
    """handle_url calls log_request after successful download."""
    from handlers import handle_url

    update = MagicMock()
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.from_user.id = 123
    update.message.from_user.first_name = "Test"
    update.message.from_user.username = "test"
    update.message.chat.id = -100
    update.message.chat.title = "Group"
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()
    update.message.reply_text.return_value = MagicMock()
    update.message.reply_text.return_value.edit_text = AsyncMock()
    update.message.reply_video = AsyncMock()

    context = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.is_valid_url", return_value=True), \
         patch("handlers.extract_urls", return_value=["https://youtube.com/watch?v=abc"]), \
         patch("handlers.get_metadata", return_value={"title": "Test Video", "duration": 60, "format": "720p"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.log_request") as mock_log:
        # Mock the downloaded file
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024*1024), \
             patch("handlers.cleanup_file"), \
             patch("builtins.open", MagicMock()):
            await handle_url(update, context)

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert call_kwargs["url"] == "https://youtube.com/watch?v=abc"
        assert call_kwargs["platform"] == "youtube"
        assert call_kwargs["content_type"] == "video"


@pytest.mark.asyncio
async def test_handle_url_logs_error_on_exception():
    """handle_url calls log_error when download raises an exception."""
    from handlers import handle_url

    update = MagicMock()
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.from_user.id = 123
    update.message.from_user.first_name = "Test"
    update.message.from_user.username = "test"
    update.message.chat.id = -100
    update.message.chat.title = "Group"
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()
    update.message.reply_text.return_value = MagicMock()
    update.message.reply_text.return_value.edit_text = AsyncMock()

    context = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.is_valid_url", return_value=True), \
         patch("handlers.extract_urls", return_value=["https://youtube.com/watch?v=abc"]), \
         patch("handlers.get_metadata", return_value={"title": "Test Video", "duration": 60, "format": "720p"}), \
         patch("handlers.download_video", side_effect=Exception("Network error")), \
         patch("handlers.log_error") as mock_error:
        with patch("handlers.cleanup_file"):
            await handle_url(update, context)

        mock_error.assert_called_once()
        call_kwargs = mock_error.call_args[1]
        assert call_kwargs["url"] == "https://youtube.com/watch?v=abc"
        assert call_kwargs["platform"] == "youtube"
        assert "Network error" in call_kwargs["error"]
