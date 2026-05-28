import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers import start_command, help_command, handle_url, _download_and_send

@pytest.fixture
def update():
    u = MagicMock()
    u.message = AsyncMock()
    u.message.from_user = MagicMock()
    u.message.from_user.id = 123456
    u.message.text = ""
    u.message.reply_text = AsyncMock()
    u.message.message_id = 42
    u.effective_chat = MagicMock()
    u.effective_chat.id = 123456
    return u

@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.bot_data = {"bot_username": "testbot"}
    return ctx

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
async def test_handle_url_processes_all_urls(update, context):
    """handle_url processes every URL in the message, not just the first."""
    update.message.text = "https://youtube.com/watch?v=abc https://tiktok.com/@user/video/123"
    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.log_request"):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)
        # Both URLs should have been processed
        assert update.message.reply_video.call_count == 2

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
        # Verify reply_parameters are included
        kwargs = update.message.reply_text.call_args[1]
        assert "reply_parameters" in kwargs
        assert kwargs["reply_parameters"] == {"message_id": update.message.message_id}


@pytest.mark.asyncio
async def test_download_and_send_replies_with_video():
    """_download_and_send calls reply_video with reply_parameters on success."""
    update = MagicMock()
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.message_id = 99
    update.message.from_user.id = 123
    update.message.from_user.first_name = "Test"
    update.message.from_user.username = "test"
    update.message.chat.id = -100
    update.message.chat.title = "Group"
    update.message.chat.type = "group"
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test Video", "duration": 60, "format": "720p"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.log_request") as mock_log:
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024*1024), \
             patch("handlers.cleanup_file"), \
             patch("builtins.open", MagicMock()):
            await _download_and_send(update, context, "https://youtube.com/watch?v=abc")

        update.message.reply_video.assert_called_once()
        kwargs = update.message.reply_video.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": 99}

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args[1]
        assert call_kwargs["url"] == "https://youtube.com/watch?v=abc"
        assert call_kwargs["platform"] == "youtube"
        assert call_kwargs["content_type"] == "video"


@pytest.mark.asyncio
async def test_download_and_send_logs_error_on_exception():
    """_download_and_send calls log_error when download raises an exception."""
    update = MagicMock()
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.message_id = 99
    update.message.from_user.id = 123
    update.message.from_user.first_name = "Test"
    update.message.from_user.username = "test"
    update.message.chat.id = -100
    update.message.chat.title = "Group"
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test Video", "duration": 60, "format": "720p"}), \
         patch("handlers.download_video", side_effect=Exception("Network error")), \
         patch("handlers.log_error") as mock_error:
        with patch("handlers.cleanup_file"):
            await _download_and_send(update, context, "https://youtube.com/watch?v=abc")

        mock_error.assert_called_once()
        call_kwargs = mock_error.call_args[1]
        assert call_kwargs["url"] == "https://youtube.com/watch?v=abc"
        assert call_kwargs["platform"] == "youtube"
        assert "Network error" in call_kwargs["error"]

        # Error reply should include reply_parameters
        update.message.reply_text.assert_called_once()
        kwargs = update.message.reply_text.call_args[1]
        assert "reply_parameters" in kwargs
        assert kwargs["reply_parameters"] == {"message_id": 99}


@pytest.mark.asyncio
async def test_download_and_send_unsupported_platform():
    """_download_and_send replies with unsupported message for unknown platforms."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("handlers.detect_platform", return_value=None):
        await _download_and_send(update, context, "https://example.com/video")
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Unsupported" in text
        kwargs = update.message.reply_text.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": 42}


@pytest.mark.asyncio
async def test_download_and_send_metadata_failure():
    """_download_and_send replies when metadata fetch fails."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value=None):
        await _download_and_send(update, context, "https://youtube.com/watch?v=abc")
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Could not fetch video info" in text
        kwargs = update.message.reply_text.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": 42}


@pytest.mark.asyncio
async def test_handle_url_no_urls_found(update, context):
    """handle_url replies when extract_urls returns empty."""
    update.message.text = "https://example.com"
    with patch("handlers.is_valid_url", return_value=True), \
         patch("handlers.extract_urls", return_value=[]):
        await handle_url(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "valid URL" in text
        kwargs = update.message.reply_text.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": update.message.message_id}
