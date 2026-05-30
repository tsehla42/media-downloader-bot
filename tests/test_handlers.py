import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram.constants import ChatAction
from handlers import start_command, help_command, handle_url, _download_and_send, caption_command, audio_command, _has_video_available, ytmusic_callback

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
    ctx.bot.send_chat_action = AsyncMock()
    ctx.user_data = {}
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
async def test_caption_command_toggle(update, context):
    update.message.text = "/caption on"
    await caption_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Captions enabled" in text

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
         patch("builtins.open", MagicMock()):
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
         patch("handlers.download_video", return_value=True):
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024*1024), \
             patch("handlers.cleanup_file"), \
             patch("builtins.open", MagicMock()):
            await _download_and_send(update, context, "https://youtube.com/watch?v=abc")

        update.message.reply_video.assert_called_once()
        kwargs = update.message.reply_video.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": 99}


@pytest.mark.asyncio
async def test_download_and_send_logs_error_on_exception():
    """_download_and_send replies with error message when download raises an exception."""
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
         patch("handlers.download_video", side_effect=Exception("Network error")):
        with patch("handlers.cleanup_file"):
            await _download_and_send(update, context, "https://youtube.com/watch?v=abc")

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
async def test_handle_url_starts_typing_immediately():
    """handle_url starts typing immediately when message received."""
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
    context.bot.send_chat_action = AsyncMock()

    mock_typing_task = MagicMock()

    async def fake_start_typing(chat_id, bot):
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        return mock_typing_task

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test Video", "duration": 60, "format": "720p"}), \
         patch("handlers.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers._start_typing", side_effect=fake_start_typing):
        await handle_url(update, context)

    # Verify typing action was sent immediately
    context.bot.send_chat_action.assert_called()
    call_args = context.bot.send_chat_action.call_args
    assert call_args[1]["chat_id"] == -100
    assert call_args[1]["action"] == ChatAction.TYPING


@pytest.mark.asyncio
async def test_handle_url_starts_typing_for_audio():
    """handle_url starts typing for /audio command."""
    update = MagicMock()
    update.message.text = "/audio https://youtube.com/watch?v=abc"
    update.message.message_id = 42
    update.message.from_user.id = 123456
    update.message.chat.id = 123456
    update.message.reply_audio = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    mock_typing_task = MagicMock()

    async def fake_start_typing(chat_id, bot):
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        return mock_typing_task

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers._start_typing", side_effect=fake_start_typing):
        await handle_url(update, context)

    context.bot.send_chat_action.assert_called()
    call_args = context.bot.send_chat_action.call_args
    assert call_args[1]["chat_id"] == 123456
    assert call_args[1]["action"] == ChatAction.TYPING
    assert call_args[1]["action"] == ChatAction.TYPING


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


@pytest.mark.asyncio
async def test_handle_url_group_ignores_unsupported_urls(update, context):
    """In groups, unsupported URLs are silently ignored (no error reply)."""
    update.message.text = "https://example.com/video"
    update.effective_chat.type = "group"

    with patch("handlers.detect_platform", return_value=None):
        await handle_url(update, context)
        # Should NOT reply with error in groups
        update.message.reply_text.assert_not_called()

@pytest.mark.asyncio
async def test_handle_url_group_processes_supported_urls(update, context):
    """In groups, supported URLs are processed normally."""
    update.message.text = "https://youtube.com/watch?v=abc"
    update.effective_chat.type = "group"

    mock_typing_task = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("handlers._start_typing", return_value=mock_typing_task):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)
        update.message.reply_video.assert_called_once()
        update.message.reply_text.assert_not_called()
        mock_typing_task.cancel.assert_called_once()

@pytest.mark.asyncio
async def test_handle_url_group_mixed_urls(update, context):
    """In groups, only supported URLs are downloaded, unsupported are ignored."""
    update.message.text = "https://example.com/video https://youtube.com/watch?v=abc"
    update.effective_chat.type = "group"

    def mock_detect_platform(url):
        if "youtube" in url:
            return "youtube"
        return None

    mock_typing_task = MagicMock()

    with patch("handlers.detect_platform", side_effect=mock_detect_platform), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("handlers._start_typing", return_value=mock_typing_task):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)
        # Only YouTube URL should be processed
        update.message.reply_video.assert_called_once()
        update.message.reply_text.assert_not_called()
        mock_typing_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_handle_url_group_shows_error_for_failed_metadata(update, context):
    """In groups, error messages are shown when supported URLs fail to download."""
    update.message.text = "https://youtube.com/watch?v=abc"
    update.effective_chat.type = "group"

    mock_typing_task = MagicMock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value=None), \
         patch("handlers._start_typing", return_value=mock_typing_task):
        await handle_url(update, context)
        # Should show error message for failed metadata
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Could not fetch video info" in text
        mock_typing_task.cancel.assert_called_once()

@pytest.mark.asyncio
async def test_handle_url_p2p_still_shows_errors(update, context):
    """In P2P, unsupported URLs still show error message."""
    update.message.text = "https://example.com/video"
    update.effective_chat.type = "private"

    with patch("handlers.detect_platform", return_value=None):
        await handle_url(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "Unsupported" in text

@pytest.mark.asyncio
async def test_handle_url_group_respects_allowlist(update, context):
    """Groups not in ALLOWED_GROUP_IDS are ignored."""
    update.message.text = "https://youtube.com/watch?v=abc"
    update.effective_chat.type = "group"
    update.effective_chat.id = -999999

    with patch("handlers.ALLOWED_GROUP_IDS", [-100100100]), \
         patch("handlers.detect_platform", return_value="youtube"):
        await handle_url(update, context)
        # Should not process because group not in allowlist
        update.message.reply_video.assert_not_called()


def test_has_video_available_with_mp4():
    """_has_video_available returns True for mp4 metadata."""
    assert _has_video_available({"ext": "mp4"}) is True


def test_has_video_available_with_webm():
    """_has_video_available returns True for webm metadata."""
    assert _has_video_available({"ext": "webm"}) is True


def test_has_video_available_with_m4a():
    """_has_video_available returns False for m4a (audio-only) metadata."""
    assert _has_video_available({"ext": "m4a"}) is False


def test_has_video_available_with_mp3():
    """_has_video_available returns False for mp3 (audio-only) metadata."""
    assert _has_video_available({"ext": "mp3"}) is False


def test_has_video_available_missing_ext():
    """_has_video_available returns False when ext key is missing."""
    assert _has_video_available({}) is False


@pytest.mark.asyncio
async def test_ytmusic_with_video_sends_inline_keyboard():
    """YouTube Music with video available shows inline keyboard instead of downloading."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.reply_text = AsyncMock()
    update.message.reply_audio = AsyncMock()
    update.message.reply_video = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test Song", "ext": "mp4"}):
        await _download_and_send(update, context, "https://music.youtube.com/watch?v=abc")

    # Should NOT send audio or video directly
    update.message.reply_audio.assert_not_called()
    update.message.reply_video.assert_not_called()

    # Should reply with inline keyboard
    update.message.reply_text.assert_called_once()
    kwargs = update.message.reply_text.call_args[1]
    assert "reply_markup" in kwargs
    markup = kwargs["reply_markup"]
    from telegram import InlineKeyboardMarkup
    assert isinstance(markup, InlineKeyboardMarkup)
    buttons = markup.inline_keyboard[0]
    assert len(buttons) == 3
    assert buttons[0].text == "Audio"
    assert buttons[1].text == "Video"
    assert buttons[2].text == "Audio + Video"

    # Verify callback data format
    assert buttons[0].callback_data == "ytm|42|audio"
    assert buttons[1].callback_data == "ytm|42|video"
    assert buttons[2].callback_data == "ytm|42|both"

    # Verify pending request stored in user_data
    assert 42 in context.user_data
    assert context.user_data[42]["url"] == "https://music.youtube.com/watch?v=abc"
    assert context.user_data[42]["title"] == "Test Song"

    # Verify request marked as success
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_ytmusic_callback_audio_choice():
    """Callback with 'audio' choice downloads audio and deletes question message."""
    from handlers import ytmusic_callback

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "ytm|42|audio"
    update.callback_query.message = MagicMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_audio = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.from_user = MagicMock()
    update.effective_message.from_user.id = 42

    context = MagicMock()
    context.user_data = {42: {"url": "https://music.youtube.com/watch?v=abc", "title": "Test Song"}}
    context.bot.send_chat_action = AsyncMock()

    with patch("handlers.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        await ytmusic_callback(update, context)

    update.callback_query.message.delete.assert_called_once()
    update.callback_query.answer.assert_called_once()
    assert 42 not in context.user_data


@pytest.mark.asyncio
async def test_ytmusic_callback_video_choice():
    """Callback with 'video' choice downloads video and deletes question message."""
    from handlers import ytmusic_callback

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "ytm|42|video"
    update.callback_query.message = MagicMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_video = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.from_user = MagicMock()
    update.effective_message.from_user.id = 42

    context = MagicMock()
    context.user_data = {42: {"url": "https://music.youtube.com/watch?v=abc", "title": "Test Song"}}
    context.bot.send_chat_action = AsyncMock()

    with patch("handlers.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        await ytmusic_callback(update, context)

    update.callback_query.message.delete.assert_called_once()
    update.callback_query.answer.assert_called_once()
    assert 42 not in context.user_data


@pytest.mark.asyncio
async def test_ytmusic_callback_both_choice():
    """Callback with 'both' choice downloads video then audio."""
    from handlers import ytmusic_callback

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "ytm|42|both"
    update.callback_query.message = MagicMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.effective_message = MagicMock()
    update.effective_message.reply_video = AsyncMock()
    update.effective_message.reply_audio = AsyncMock()
    update.effective_message.reply_text = AsyncMock()
    update.effective_message.from_user = MagicMock()
    update.effective_message.from_user.id = 42

    context = MagicMock()
    context.user_data = {42: {"url": "https://music.youtube.com/watch?v=abc", "title": "Test Song"}}
    context.bot.send_chat_action = AsyncMock()

    with patch("handlers.download_video", return_value=True), \
         patch("handlers.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        await ytmusic_callback(update, context)

    update.callback_query.message.delete.assert_called_once()
    assert 42 not in context.user_data


@pytest.mark.asyncio
async def test_ytmusic_callback_expired_request():
    """Callback with no pending data answers 'expired' and does not delete."""
    from handlers import ytmusic_callback

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "ytm|999|audio"
    update.callback_query.message = MagicMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    await ytmusic_callback(update, context)

    update.callback_query.answer.assert_called_once()
    answer_text = update.callback_query.answer.call_args[0][0]
    assert "expired" in answer_text.lower()
    update.callback_query.message.delete.assert_not_called()


@pytest.mark.asyncio
async def test_ytmusic_callback_ttl_expired():
    """Callback with stale pending data (old timestamp) answers expired."""
    from handlers import ytmusic_callback

    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "ytm|42|audio"
    update.callback_query.message = MagicMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()

    import time
    stale_timestamp = time.time() - 600  # 10 minutes ago
    context = MagicMock()
    context.user_data = {42: {"url": "https://music.youtube.com/watch?v=abc", "title": "Test", "timestamp": stale_timestamp}}
    context.bot.send_chat_action = AsyncMock()

    await ytmusic_callback(update, context)

    # Should answer with expired message
    update.callback_query.answer.assert_called_once()
    answer_text = update.callback_query.answer.call_args[0][0]
    assert "expired" in answer_text.lower()
    # Should NOT delete the message
    update.callback_query.message.delete.assert_not_called()
    # Pending data should be popped (cleaned up)
    assert 42 not in context.user_data
