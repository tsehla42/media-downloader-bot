import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, ChatMemberUpdated, User, Chat
from telegram.ext import ContextTypes
from handlers import handle_url, audio_command, my_chat_member_handler, _download_and_send
from platforms.youtube import ytmusic_callback, _has_video_available, _ytmusic_pending
from commands import caption_command


def _make_typing_indicator_mock():
    """Create a mock that behaves as typing_indicator (async context manager factory)."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_cm)

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
async def test_caption_command_toggle(update, context):
    update.message.text = "/caption on"
    with patch("commands.is_authorized", return_value=True):
        await caption_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Captions enabled" in text

@pytest.mark.asyncio
async def test_handle_url_processes_all_urls(update, context):
    """handle_url processes every URL in the message, not just the first."""
    update.message.text = "https://youtube.com/watch?v=abc https://tiktok.com/@user/video/123"
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("platforms.youtube.download_video", return_value=True), \
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
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=False):
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
         patch("platforms.youtube.download_video", return_value=True):
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024*1024), \
             patch("handlers.cleanup_file"), \
             patch("builtins.open", MagicMock()):
            await _download_and_send(update, context, "https://youtube.com/watch?v=abc")

        update.message.reply_video.assert_called_once()
        kwargs = update.message.reply_video.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": 99}


@pytest.mark.asyncio
async def test_reply_video_includes_supports_streaming():
    """reply_video must pass supports_streaming=True for Telegram inline playback."""
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
         patch("platforms.youtube.download_video", return_value=True):
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024*1024), \
             patch("handlers.cleanup_file"), \
             patch("builtins.open", MagicMock()):
            await _download_and_send(update, context, "https://youtube.com/watch?v=abc")

        update.message.reply_video.assert_called_once()
        kwargs = update.message.reply_video.call_args[1]
        assert kwargs.get("supports_streaming") is True


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
         patch("platforms.youtube.download_video", side_effect=Exception("Network error")):
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
        assert "Could not fetch post" in text
        kwargs = update.message.reply_text.call_args[1]
        assert kwargs["reply_parameters"] == {"message_id": 42}


@pytest.mark.asyncio
async def test_handle_url_starts_typing_immediately():
    """handle_url does NOT wrap YouTube in typing (typing handled inside download)."""
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

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test Video", "duration": 60, "format": "720p"}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)

    # YouTube: typing_indicator NOT called at handle_url level
    mock_typing.assert_not_called()


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

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)

    # typing_indicator is called once from audio_command (handle_url no longer wraps it)
    assert mock_typing.call_count == 1
    call_args = mock_typing.call_args
    assert call_args[0][0] == 123456


@pytest.mark.asyncio
async def test_audio_command_uses_title_for_filename():
    """audio_command fetches metadata and uses title in filename and reply."""
    update = MagicMock()
    update.message.text = "/audio https://youtube.com/watch?v=abc"
    update.message.message_id = 42
    update.message.from_user.id = 123456
    update.message.chat.id = 123456
    update.message.reply_audio = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.user_data = {}

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "My Test Song"}), \
         patch("handlers.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        await audio_command(update, context)

    update.message.reply_audio.assert_called_once()
    kwargs = update.message.reply_audio.call_args[1]
    assert kwargs["title"] == "My Test Song"
    assert kwargs["reply_parameters"] == {"message_id": 42}


@pytest.mark.asyncio
async def test_audio_command_no_metadata_omits_title():
    """audio_command omits title when metadata unavailable."""
    update = MagicMock()
    update.message.text = "/audio https://youtube.com/watch?v=abc"
    update.message.message_id = 42
    update.message.from_user.id = 123456
    update.message.chat.id = 123456
    update.message.reply_audio = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.user_data = {}

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value=None), \
         patch("handlers.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        await audio_command(update, context)

    update.message.reply_audio.assert_called_once()
    kwargs = update.message.reply_audio.call_args[1]
    assert "title" not in kwargs
    assert kwargs["reply_parameters"] == {"message_id": 42}


@pytest.mark.asyncio
async def test_handle_url_no_urls_found(update, context):
    """handle_url replies when extract_urls returns empty."""
    update.message.text = "https://example.com"
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.is_valid_url", return_value=True), \
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

    with patch("handlers.detect_platform", return_value=None), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=False):
        await handle_url(update, context)
        # Should NOT reply with error in groups
        update.message.reply_text.assert_not_called()

@pytest.mark.asyncio
async def test_handle_url_group_processes_supported_urls(update, context):
    """In groups, supported URLs are processed normally."""
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.reply_to_message = None
    update.effective_chat.type = "group"

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)
        update.message.reply_video.assert_called_once()
        update.message.reply_text.assert_not_called()
        # YouTube: typing NOT called at handle_url level
        mock_typing.assert_not_called()

@pytest.mark.asyncio
async def test_handle_url_group_mixed_urls(update, context):
    """In groups, only supported URLs are downloaded, unsupported are ignored."""
    update.message.text = "https://example.com/video https://youtube.com/watch?v=abc"
    update.message.reply_to_message = None
    update.effective_chat.type = "group"

    def mock_detect_platform(url):
        if "youtube" in url:
            return "youtube"
        return None

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.detect_platform", side_effect=mock_detect_platform), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=False):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)
        # Only YouTube URL should be processed
        update.message.reply_video.assert_called_once()
        update.message.reply_text.assert_not_called()
        # YouTube-only: typing NOT called at handle_url level
        mock_typing.assert_not_called()


@pytest.mark.asyncio
async def test_handle_url_group_silently_ignores_failed_metadata(update, context):
    """In groups, metadata failures are silently ignored (no error message)."""
    update.message.text = "https://youtube.com/watch?v=abc"
    update.effective_chat.type = "group"

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value=None), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)
        # Should NOT show error message in groups (silent=True by default)
        update.message.reply_text.assert_not_called()
        # YouTube: typing NOT called at handle_url level
        mock_typing.assert_not_called()

@pytest.mark.asyncio
async def test_handle_url_p2p_still_shows_errors(update, context):
    """In P2P, unsupported URLs still show error message."""
    update.message.text = "https://example.com/video"
    update.effective_chat.type = "private"

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=False):
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

    with patch("auth.ALLOWED_GROUP_IDS", [-100100100]), \
         patch("handlers.detect_platform", return_value="youtube"):
        await handle_url(update, context)
        # Should not process because group not in allowlist
        update.message.reply_video.assert_not_called()


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

    metadata = {
        "title": "Test Song",
        "ext": "mp4",
        "formats": [
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
            {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640020", "acodec": "none"},
        ],
    }
    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value=metadata):
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
    assert buttons[2].text == "Video + Audio"

    # Verify callback data format
    assert buttons[0].callback_data == "ytm|42|audio"
    assert buttons[1].callback_data == "ytm|42|video"
    assert buttons[2].callback_data == "ytm|42|both"

    # Verify pending request stored in shared dict
    assert 42 in _ytmusic_pending
    assert _ytmusic_pending[42]["url"] == "https://music.youtube.com/watch?v=abc"
    assert _ytmusic_pending[42]["title"] == "Test Song"

    # Verify request marked as success
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_ytmusic_audio_only_sends_audio_directly():
    """When YouTube Music has no video (m4a), bot sends audio without keyboard."""
    update = MagicMock()
    update.message.text = "https://music.youtube.com/watch?v=abc"
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_audio = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test Song", "ext": "m4a"}), \
         patch("platforms.youtube.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        await _download_and_send(update, context, "https://music.youtube.com/watch?v=abc")

    # Should send audio directly, no keyboard
    update.message.reply_audio.assert_called_once()
    update.message.reply_text.assert_not_called()
    assert 42 not in context.user_data



@pytest.mark.asyncio
async def test_download_and_send_instagram_uses_gallery_dl_fallback():
    """When yt-dlp video fails on Instagram, tries gallery-dl for images."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="instagram"), \
         patch("platforms.instagram.download_video", return_value=False), \
         patch("platforms.instagram.download_gallery_dl_images", return_value=["/tmp/img.jpg"]), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.cleanup_file"):
        await _download_and_send(update, context, "https://instagram.com/p/ABC123/")

    update.message.reply_photo.assert_called_once()


@pytest.mark.asyncio
async def test_download_and_send_instagram_gallery_dl_fails():
    """When both video and gallery-dl fail on Instagram, show error message."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="instagram"), \
         patch("platforms.instagram.download_video", return_value=False), \
         patch("platforms.instagram.download_gallery_dl_images", return_value=[]):
        await _download_and_send(update, context, "https://instagram.com/p/ABC123/")

    update.message.reply_photo.assert_not_called()
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Could not fetch post" in text


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_added():
    """Handler logs when bot is added to a chat."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "left"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "member"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_bot_added_to_chat") as mock_log, \
         patch("handlers.is_bot_admin", return_value=True):
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_removed():
    """Handler logs when bot is removed from a chat."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "group"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "member"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "left"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_bot_removed_from_chat") as mock_log:
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_promoted():
    """Handler logs when bot is promoted to admin with initial rights."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "member"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "administrator"
    update.my_chat_member.new_chat_member.can_manage_chat = True
    update.my_chat_member.new_chat_member.can_delete_messages = False
    update.my_chat_member.new_chat_member.can_manage_video_chats = True
    update.my_chat_member.new_chat_member.can_restrict_members = True
    update.my_chat_member.new_chat_member.can_promote_members = False
    update.my_chat_member.new_chat_member.can_change_info = True
    update.my_chat_member.new_chat_member.can_invite_users = True
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_admin_rights_changed") as mock_log:
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][2] is None  # old_rights (was not admin)
        assert call_args[0][4] == "bot_added_as_admin"
        # Verify new rights were extracted
        new_rights = call_args[0][3]
        assert new_rights["can_manage_chat"] is True
        assert new_rights["can_delete_messages"] is False


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_demoted():
    """Handler logs when bot is demoted from admin."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "administrator"
    update.my_chat_member.old_chat_member.can_manage_chat = True
    update.my_chat_member.old_chat_member.can_delete_messages = True
    update.my_chat_member.old_chat_member.can_manage_video_chats = True
    update.my_chat_member.old_chat_member.can_restrict_members = True
    update.my_chat_member.old_chat_member.can_promote_members = False
    update.my_chat_member.old_chat_member.can_change_info = True
    update.my_chat_member.old_chat_member.can_invite_users = True
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "member"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_bot_status_changed") as mock_log:
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][2] == "administrator"
        assert call_args[0][3] == "member"


@pytest.mark.asyncio
async def test_my_chat_member_handler_ignores_no_update():
    """Handler returns early when my_chat_member is None."""
    update = MagicMock()
    update.my_chat_member = None
    context = MagicMock()

    await my_chat_member_handler(update, context)
    # No assertions needed - just verify no exception


@pytest.mark.asyncio
async def test_download_and_send_tiktok_photo_fallback():
    """When video download fails on TikTok, try gallery-dl for photos."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("handlers.get_metadata") as mock_metadata, \
         patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("builtins.open", MagicMock()), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=500000), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(update, context, "https://tiktok.com/@user/video/123")

    # Metadata should NOT be fetched for TikTok
    mock_metadata.assert_not_called()
    update.message.reply_photo.assert_called_once()
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_download_and_send_tiktok_multiple_photos():
    """When video download fails on TikTok with multiple photos, send as media group."""
    import io
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_media_group = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    def fake_open(path, mode="r"):
        return io.BytesIO(b"\x89PNG fake image data")

    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt1.jpg", "/tmp/tt2.jpg", "/tmp/tt3.jpg"]), \
         patch("builtins.open", side_effect=fake_open), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=500000), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(update, context, "https://tiktok.com/@user/gallery/456")

    update.message.reply_media_group.assert_called_once()
    assert context.user_data["_content_type"] == "image"
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_download_and_send_tiktok_both_fail():
    """When both video download and gallery-dl fail on TikTok, show error."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=[]), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(update, context, "https://tiktok.com/@user/photo/789")

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Could not fetch post" in text


@pytest.mark.asyncio
async def test_download_and_send_tiktok_delegates_immediately():
    """TikTok is delegated to handle_tiktok without fetching metadata first."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("handlers.get_metadata") as mock_metadata, \
         patch("platforms.tiktok.download_video", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=500000), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(update, context, "https://tiktok.com/@user/video/123")

    # Metadata should NOT be fetched for TikTok
    mock_metadata.assert_not_called()
    update.message.reply_video.assert_called_once()
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_download_and_send_tiktok_login_required_p2p():
    """DownloadAuthRequired in P2P shows login-required message."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.chat.type = "private"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    from downloader import DownloadAuthRequired
    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("platforms.tiktok.download_video", side_effect=DownloadAuthRequired("Log in for access")), \
         patch("platforms.tiktok.get_metadata", return_value=None), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(update, context, "https://tiktok.com/@user/video/123")

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "restricted access" in text
    assert "login" in text


@pytest.mark.asyncio
async def test_download_and_send_tiktok_login_required_group_silent():
    """DownloadAuthRequired in group (normal URL) is silent."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    from downloader import DownloadAuthRequired
    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("handlers.is_group_chat", return_value=True), \
         patch("platforms.tiktok.download_video", side_effect=DownloadAuthRequired("Log in for access")), \
         patch("platforms.tiktok.get_metadata", return_value=None), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(update, context, "https://tiktok.com/@user/video/123")

    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_download_and_send_tiktok_login_required_reply_to_retry():
    """DownloadAuthRequired via reply-to-retry shows login-required message."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    from downloader import DownloadAuthRequired
    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("platforms.tiktok.download_video", side_effect=DownloadAuthRequired("Log in for access")), \
         patch("platforms.tiktok.get_metadata", return_value=None), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"):
        await _download_and_send(
            update, context, "https://tiktok.com/@user/video/123",
            silent=False, reply_to_message_id=100,
        )

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "restricted access" in text
    kwargs = update.message.reply_text.call_args[1]
    assert kwargs["reply_parameters"] == {"message_id": 100}


@pytest.mark.asyncio
async def test_download_and_send_instagram_delegates_immediately():
    """Instagram is delegated to handle_instagram without fetching metadata first."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="instagram"), \
         patch("handlers.get_metadata") as mock_metadata, \
         patch("platforms.instagram.download_video", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=500000), \
         patch("platforms.instagram.cleanup_file"), \
         patch("platforms.instagram.cleanup_dir"):
        await _download_and_send(update, context, "https://instagram.com/p/ABC123/")

    # Metadata should NOT be fetched in _download_and_send for Instagram
    mock_metadata.assert_not_called()
    update.message.reply_video.assert_called_once()
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_download_and_send_skips_large_youtube_video():
    """YouTube video >50MB is skipped silently (no error message)."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.effective_chat.type = "group"
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={
             "title": "Big Video",
             "filesize_approx": 60 * 1024 * 1024,  # 60MB
         }), \
         patch("handlers.cleanup_file"):
        await _download_and_send(update, context, "https://youtube.com/watch?v=big")

    # Should NOT download or send anything
    update.message.reply_video.assert_not_called()
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_download_and_send_proceeds_with_small_youtube_video():
    """YouTube video <50MB is downloaded and sent."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={
             "title": "Small Video",
             "filesize_approx": 10 * 1024 * 1024,  # 10MB
         }), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=10*1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        await _download_and_send(update, context, "https://youtube.com/watch?v=small")

    update.message.reply_video.assert_called_once()


@pytest.mark.asyncio
async def test_download_and_send_proceeds_with_unknown_size_youtube():
    """YouTube video with no size info is downloaded (optimistic)."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Unknown Size Video"}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=5*1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()):
        await _download_and_send(update, context, "https://youtube.com/watch?v=unknown")

    update.message.reply_video.assert_called_once()


@pytest.mark.asyncio
async def test_download_and_send_skips_youtube_metadata_failure_in_group():
    """YouTube metadata failure in group is skipped silently (no error message)."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.effective_chat.type = "group"
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value=None), \
         patch("handlers.cleanup_file"):
        await _download_and_send(update, context, "https://youtube.com/watch?v=private")

    update.message.reply_video.assert_not_called()
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_download_and_send_silent_false_shows_error_in_group():
    """When silent=False, error messages are shown even in group chats."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value=None):
        await _download_and_send(update, context, "https://example.com/video", silent=False)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Unsupported" in text


@pytest.mark.asyncio
async def test_download_and_send_reply_to_message_id():
    """When reply_to_message_id is set, reply to that message."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value=None):
        await _download_and_send(
            update, context, "https://example.com/video",
            reply_to_message_id=99,
        )

    update.message.reply_text.assert_called_once()
    kwargs = update.message.reply_text.call_args[1]
    assert kwargs["reply_parameters"] == {"message_id": 99}


@pytest.mark.asyncio
async def test_download_and_send_skips_large_youtube_in_p2p():
    """YouTube video >50MB is skipped in P2P too (no download attempted)."""
    update = MagicMock()
    update.message.message_id = 42
    update.message.from_user.id = 123
    update.message.chat.type = "private"
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={
             "title": "Big Video",
             "filesize_approx": 60 * 1024 * 1024,
         }), \
         patch("handlers.cleanup_file"):
        await _download_and_send(update, context, "https://youtube.com/watch?v=big")

    # Should NOT download, but SHOULD show error in P2P
    update.message.reply_video.assert_not_called()
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "50MB" in text


@pytest.mark.asyncio
async def test_handle_url_youtube_typing_only_during_download():
    """For YouTube, typing indicator should only wrap the download phase, not metadata fetch."""
    update = MagicMock()
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.message_id = 99
    update.message.from_user.id = 123
    update.message.chat.id = -100
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot_data = {"bot_username": "testbot"}

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test", "filesize_approx": 5*1024*1024}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=5*1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)

    # typing_indicator should NOT be called at handle_url level for YouTube
    mock_typing.assert_not_called()
    update.message.reply_video.assert_called_once()


@pytest.mark.asyncio
async def test_handle_url_non_youtube_uses_typing_wrapper():
    """For non-YouTube platforms, typing indicator wraps the full flow."""
    update = MagicMock()
    update.message.text = "https://tiktok.com/@user/video/123"
    update.message.message_id = 99
    update.message.from_user.id = 123
    update.message.chat.id = 100
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot_data = {"bot_username": "testbot"}

    mock_typing = _make_typing_indicator_mock()

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="tiktok"), \
         patch("handlers.get_metadata") as mock_metadata, \
         patch("platforms.tiktok.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=500000), \
         patch("handlers.cleanup_file"), \
         patch("platforms.tiktok.cleanup_file"), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)

    # typing_indicator should be called for non-YouTube
    mock_typing.assert_called_once()


# --- reply-to-retry tests (now handled inside handle_url) ---


@pytest.mark.asyncio
async def test_handle_url_reply_to_retry_downloads_on_bot_mention():
    """Reply to a message with URL + bot mention triggers download."""
    update = MagicMock()
    update.message.text = "@mediabot try this"
    update.message.message_id = 200
    update.message.from_user.id = 123
    update.message.chat.id = 100
    update.message.chat.type = "private"
    update.message.reply_video = AsyncMock()
    update.message.reply_text = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "https://youtube.com/watch?v=abc"
    update.message.reply_to_message.message_id = 100

    context = MagicMock()
    context.bot_data = {"bot_username": "mediabot"}
    context.user_data = {}

    mock_typing = _make_typing_indicator_mock()
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={"title": "Test", "filesize_approx": 5*1024*1024}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=5*1024*1024), \
         patch("handlers.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)

    update.message.reply_video.assert_called_once()
    # Should reply to original message (100), not the reply (200)
    kwargs = update.message.reply_video.call_args[1]
    assert kwargs["reply_parameters"] == {"message_id": 100}


@pytest.mark.asyncio
async def test_handle_url_reply_ignores_no_bot_mention():
    """Reply without bot mention is silently ignored (no URL in message text)."""
    update = MagicMock()
    update.message.text = "nice video"
    update.message.message_id = 200
    update.message.from_user.id = 123
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "https://youtube.com/watch?v=abc"

    context = MagicMock()
    context.bot_data = {"bot_username": "mediabot"}

    with patch("handlers.detect_platform") as mock_detect:
        await handle_url(update, context)
        mock_detect.assert_not_called()


@pytest.mark.asyncio
async def test_handle_url_reply_ignores_no_url_in_replied_message():
    """Reply to a message with no URL is silently ignored."""
    update = MagicMock()
    update.message.text = "@mediabot what was that"
    update.message.message_id = 200
    update.message.from_user.id = 123
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "just a text message"

    context = MagicMock()
    context.bot_data = {"bot_username": "mediabot"}

    with patch("handlers.detect_platform") as mock_detect:
        await handle_url(update, context)
        mock_detect.assert_not_called()


@pytest.mark.asyncio
async def test_handle_url_reply_shows_limit_for_large_youtube():
    """Reply to YouTube >50MB shows 'above limit' message."""
    update = MagicMock()
    update.message.text = "@mediabot try this"
    update.message.message_id = 200
    update.message.from_user.id = 123
    update.message.chat.id = 100
    update.message.chat.type = "group"
    update.message.reply_text = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "https://youtube.com/watch?v=big"
    update.message.reply_to_message.message_id = 100

    context = MagicMock()
    context.bot_data = {"bot_username": "mediabot"}
    context.user_data = {}

    mock_typing = _make_typing_indicator_mock()
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value="youtube"), \
         patch("handlers.get_metadata", return_value={
             "title": "Big Video",
             "filesize_approx": 60 * 1024 * 1024,
         }), \
         patch("handlers.cleanup_file"), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "50MB" in text
    # Should reply to original message
    kwargs = update.message.reply_text.call_args[1]
    assert kwargs["reply_parameters"] == {"message_id": 100}


@pytest.mark.asyncio
async def test_handle_url_reply_unsupported_platform():
    """Reply to unsupported platform URL shows error."""
    update = MagicMock()
    update.message.text = "@mediabot try this"
    update.message.message_id = 200
    update.message.from_user.id = 123
    update.message.reply_text = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "https://example.com/video"

    context = MagicMock()
    context.bot_data = {"bot_username": "mediabot"}

    mock_typing = _make_typing_indicator_mock()
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.typing_indicator", mock_typing):
        await handle_url(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Unsupported" in text


@pytest.mark.asyncio
async def test_handle_url_reply_rejects_unauthorized():
    """Unauthorized user gets error message."""
    update = MagicMock()
    update.message.text = "@mediabot try this"
    update.message.message_id = 200
    update.message.from_user.id = 999
    update.message.reply_text = AsyncMock()
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "https://youtube.com/watch?v=abc"

    context = MagicMock()
    context.bot_data = {"bot_username": "mediabot"}

    with patch("handlers.is_authorized", return_value=False):
        await handle_url(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "not authorized" in text


# --- handle_gallery_dl_fallback tests ---


@pytest.mark.asyncio
async def test_gallery_dl_fallback_images_success(update, context):
    """handle_gallery_dl_fallback sends images when download succeeds."""
    from handlers import handle_gallery_dl_fallback

    with patch("handlers.download_gallery_dl_images", return_value=["/tmp/img.jpg"]), \
         patch("handlers.send_images", new_callable=AsyncMock, return_value=1024) as mock_send, \
         patch("handlers.cleanup_dir"), \
         patch("handlers.download_gallery_dl_video", return_value=None):
        result = await handle_gallery_dl_fallback(update, context, "https://pinterest.com/pin/123456/")

    assert result is True
    mock_send.assert_called_once()
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_handle_url_routes_pinterest_to_gallery_dl_fallback(update, context):
    """Pinterest URL triggers gallery-dl fallback instead of 'Unsupported platform'."""
    update.message.text = "https://pinterest.com/pin/123456/"

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset()), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset(["pinterest.com"])), \
         patch("handlers.extract_domain", return_value="pinterest.com"), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=True) as mock_fallback:
        await handle_url(update, context)

    mock_fallback.assert_called_once()
    # Should NOT show "Unsupported platform" since fallback was successful
    update.message.reply_text.assert_not_called()


# --- gallery-dl fallback comprehensive tests ---


@pytest.mark.asyncio
async def test_gallery_dl_fallback_video_success(update, context):
    """gallery-dl fallback sends video when images fail but video succeeds."""
    update.message.text = "https://example.com/post"
    update.message.reply_video = AsyncMock()

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset(["example.com"])), \
         patch("handlers.extract_domain", return_value="example.com"), \
         patch("handlers.download_gallery_dl_images", return_value=[]), \
         patch("handlers.download_gallery_dl_video", return_value="/tmp/video.mp4"), \
         patch("handlers.cleanup_dir"), \
         patch("os.path.getsize", return_value=2*1024*1024), \
         patch("builtins.open", MagicMock()):
        await handle_url(update, context)

    update.message.reply_video.assert_called_once()
    assert context.user_data["_request_success"] is True
    assert context.user_data["_content_type"] == "video"


@pytest.mark.asyncio
async def test_gallery_dl_fallback_failure_silent_group(update, context):
    """gallery-dl fallback failure in group is silent (no message)."""
    update.message.text = "https://example.com/post"
    update.effective_chat.type = "group"

    with patch("handlers.detect_platform", return_value=None), \
         patch("handlers.download_gallery_dl_images", return_value=[]), \
         patch("handlers.download_gallery_dl_video", return_value=None), \
         patch("handlers.cleanup_dir"):
        await handle_url(update, context)

    update.message.reply_text.assert_not_called()
    update.message.reply_video.assert_not_called()


@pytest.mark.asyncio
async def test_gallery_dl_fallback_failure_p2p_shows_error(update, context):
    """gallery-dl fallback failure in P2P shows 'Unsupported platform'."""
    update.message.text = "https://example.com/post"
    update.effective_chat.type = "private"

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.download_gallery_dl_images", return_value=[]), \
         patch("handlers.download_gallery_dl_video", return_value=None), \
         patch("handlers.cleanup_dir"):
        await handle_url(update, context)

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Unsupported" in text


@pytest.mark.asyncio
async def test_gallery_dl_fallback_not_installed(update, context):
    """gallery-dl fallback gracefully skips when gallery-dl is not installed."""
    update.message.text = "https://example.com/post"
    update.effective_chat.type = "group"

    with patch("handlers.detect_platform", return_value=None), \
         patch("handlers.download_gallery_dl_images", side_effect=FileNotFoundError("gallery-dl not found")), \
         patch("handlers.download_gallery_dl_video", side_effect=FileNotFoundError("gallery-dl not found")), \
         patch("handlers.cleanup_dir"):
        # Should not raise, should not show error
        await handle_url(update, context)

    update.message.reply_text.assert_not_called()
    update.message.reply_video.assert_not_called()


@pytest.mark.asyncio
async def test_gallery_dl_fallback_timeout(update, context):
    """gallery-dl fallback handles subprocess timeout gracefully."""
    import subprocess as sp
    update.message.text = "https://example.com/slow-post"

    with patch("handlers.detect_platform", return_value=None), \
         patch("handlers.download_gallery_dl_images", side_effect=sp.TimeoutExpired(cmd="gallery-dl", timeout=60)), \
         patch("handlers.download_gallery_dl_video", return_value=None), \
         patch("handlers.cleanup_dir"):
        # Should not raise
        await handle_url(update, context)


@pytest.mark.asyncio
async def test_handle_url_mixed_supported_and_unsupported(update, context):
    """Mixed message with YT and Pinterest URLs processes both."""
    update.message.text = "https://youtube.com/watch?v=abc https://pinterest.com/pin/123/"

    def mock_detect_platform(url):
        if "youtube" in url:
            return "youtube"
        return None

    def mock_extract_domain(url):
        if "pinterest" in url:
            return "pinterest.com"
        return ""

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", side_effect=mock_detect_platform), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset()), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset(["pinterest.com"])), \
         patch("handlers.extract_domain", side_effect=mock_extract_domain), \
         patch("handlers.get_metadata", return_value={"title": "Test"}), \
         patch("platforms.youtube.download_video", return_value=True), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=True) as mock_fallback, \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("builtins.open", MagicMock()):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)

    # YouTube processed via _download_and_send
    assert update.message.reply_video.call_count >= 1
    # Pinterest processed via gallery-dl fallback
    mock_fallback.assert_called_once()
    # No error message
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_my_chat_member_handler_user_blocked_bot():
    """Handler logs user_blocked_bot when user blocks bot in private chat."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = 123456
    update.my_chat_member.chat.title = None
    update.my_chat_member.chat.type = "private"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "left"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "kicked"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 99999
    update.my_chat_member.from_user.first_name = "Angry"
    update.my_chat_member.from_user.username = "angry_user"

    context = MagicMock()

    with patch("handlers.log_user_blocked_bot") as mock_block_log, \
         patch("handlers.log_bot_added_to_chat") as mock_add_log, \
         patch("handlers.log_bot_removed_from_chat") as mock_remove_log:
        await my_chat_member_handler(update, context)
        mock_block_log.assert_called_once()
        mock_add_log.assert_not_called()
        mock_remove_log.assert_not_called()


@pytest.mark.asyncio
async def test_my_chat_member_handler_admin_rights_changed():
    """Handler logs when admin rights are changed (same status, different rights)."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Channel"
    update.my_chat_member.chat.type = "channel"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "administrator"
    update.my_chat_member.old_chat_member.can_manage_chat = True
    update.my_chat_member.old_chat_member.can_delete_messages = False
    update.my_chat_member.old_chat_member.can_post_messages = True
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "administrator"
    update.my_chat_member.new_chat_member.can_manage_chat = True
    update.my_chat_member.new_chat_member.can_delete_messages = True
    update.my_chat_member.new_chat_member.can_post_messages = True
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_admin_rights_changed") as mock_log:
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][4] == "bot_admin_rights_changed"
        # Verify old and new rights were passed
        old_rights = call_args[0][2]
        new_rights = call_args[0][3]
        assert old_rights["can_delete_messages"] is False
        assert new_rights["can_delete_messages"] is True


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_added_as_admin_to_channel():
    """Handler logs when bot is added as admin to a channel."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100123
    update.my_chat_member.chat.title = "My Channel"
    update.my_chat_member.chat.type = "channel"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "left"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "administrator"
    update.my_chat_member.new_chat_member.can_manage_chat = True
    update.my_chat_member.new_chat_member.can_delete_messages = True
    update.my_chat_member.new_chat_member.can_post_messages = True
    update.my_chat_member.new_chat_member.can_edit_messages = True
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_admin_rights_changed") as mock_log, \
         patch("handlers.log_bot_added_to_chat") as mock_add_log:
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()
        mock_add_log.assert_not_called()
        call_args = mock_log.call_args
        assert call_args[0][4] == "bot_added_as_admin"
        assert call_args[0][2] is None  # old_rights (was not admin)
        new_rights = call_args[0][3]
        assert new_rights["can_post_messages"] is True
        assert new_rights["can_edit_messages"] is True


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_removed_as_admin_from_channel():
    """Handler logs bot_removed_from_chat when bot is removed from channel."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100123
    update.my_chat_member.chat.title = "My Channel"
    update.my_chat_member.chat.type = "channel"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "administrator"
    update.my_chat_member.old_chat_member.can_manage_chat = True
    update.my_chat_member.old_chat_member.can_delete_messages = True
    update.my_chat_member.old_chat_member.can_post_messages = True
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "left"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_bot_removed_from_chat") as mock_remove_log:
        await my_chat_member_handler(update, context)
        mock_remove_log.assert_called_once()


@pytest.mark.asyncio
async def test_my_chat_member_handler_bot_added_as_admin_to_group():
    """Handler logs when bot is added as admin to a group with initial rights."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100456
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "member"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "administrator"
    update.my_chat_member.new_chat_member.can_manage_chat = True
    update.my_chat_member.new_chat_member.can_delete_messages = False
    update.my_chat_member.new_chat_member.can_pin_messages = True
    update.my_chat_member.new_chat_member.can_manage_topics = False
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 789
    update.my_chat_member.from_user.first_name = "Owner"
    update.my_chat_member.from_user.username = "owner"

    context = MagicMock()

    with patch("handlers.log_admin_rights_changed") as mock_log:
        await my_chat_member_handler(update, context)
        mock_log.assert_called_once()
        call_args = mock_log.call_args
        assert call_args[0][4] == "bot_added_as_admin"
        assert call_args[0][2] is None  # old_rights (was member)
        new_rights = call_args[0][3]
        assert new_rights["can_pin_messages"] is True
        assert new_rights["can_manage_topics"] is False


@pytest.mark.asyncio
async def test_my_chat_member_handler_custom_title_only_change():
    """Custom title only change fires bot_custom_title_changed, not bot_admin_rights_changed."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "administrator"
    update.my_chat_member.old_chat_member.can_manage_chat = True
    update.my_chat_member.old_chat_member.can_delete_messages = True
    update.my_chat_member.old_chat_member.can_manage_video_chats = True
    update.my_chat_member.old_chat_member.can_restrict_members = True
    update.my_chat_member.old_chat_member.can_promote_members = False
    update.my_chat_member.old_chat_member.can_change_info = True
    update.my_chat_member.old_chat_member.can_invite_users = True
    update.my_chat_member.old_chat_member.custom_title = None
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "administrator"
    update.my_chat_member.new_chat_member.can_manage_chat = True
    update.my_chat_member.new_chat_member.can_delete_messages = True
    update.my_chat_member.new_chat_member.can_manage_video_chats = True
    update.my_chat_member.new_chat_member.can_restrict_members = True
    update.my_chat_member.new_chat_member.can_promote_members = False
    update.my_chat_member.new_chat_member.can_change_info = True
    update.my_chat_member.new_chat_member.can_invite_users = True
    update.my_chat_member.new_chat_member.custom_title = "aboba"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_custom_title_changed") as mock_title_log, \
         patch("handlers.log_admin_rights_changed") as mock_rights_log:
        await my_chat_member_handler(update, context)
        mock_title_log.assert_called_once()
        mock_rights_log.assert_not_called()
        call_args = mock_title_log.call_args
        assert call_args[0][2] is None  # old_title
        assert call_args[0][3] == "aboba"  # new_title


@pytest.mark.asyncio
async def test_my_chat_member_handler_mixed_change_uses_rights_event():
    """Custom title + other rights change fires bot_admin_rights_changed (not custom_title)."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "administrator"
    update.my_chat_member.old_chat_member.can_manage_chat = True
    update.my_chat_member.old_chat_member.can_delete_messages = True
    update.my_chat_member.old_chat_member.can_manage_video_chats = True
    update.my_chat_member.old_chat_member.can_restrict_members = True
    update.my_chat_member.old_chat_member.can_promote_members = False
    update.my_chat_member.old_chat_member.can_change_info = True
    update.my_chat_member.old_chat_member.can_invite_users = True
    update.my_chat_member.old_chat_member.custom_title = None
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "administrator"
    update.my_chat_member.new_chat_member.can_manage_chat = True
    update.my_chat_member.new_chat_member.can_delete_messages = False  # changed!
    update.my_chat_member.new_chat_member.can_manage_video_chats = True
    update.my_chat_member.new_chat_member.can_restrict_members = True
    update.my_chat_member.new_chat_member.can_promote_members = False
    update.my_chat_member.new_chat_member.can_change_info = True
    update.my_chat_member.new_chat_member.can_invite_users = True
    update.my_chat_member.new_chat_member.custom_title = "aboba"  # also changed
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_custom_title_changed") as mock_title_log, \
         patch("handlers.log_admin_rights_changed") as mock_rights_log:
        await my_chat_member_handler(update, context)
        mock_title_log.assert_not_called()
        mock_rights_log.assert_called_once()
        assert mock_rights_log.call_args[0][4] == "bot_restrictions_changed"


@pytest.mark.asyncio
async def test_my_chat_member_handler_user_unblocked_bot():
    """Handler logs user_unblocked_bot when user unblocks bot in private chat."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = 123456
    update.my_chat_member.chat.title = None
    update.my_chat_member.chat.type = "private"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "kicked"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "member"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 99999
    update.my_chat_member.from_user.first_name = "User"
    update.my_chat_member.from_user.username = "user"

    context = MagicMock()

    with patch("handlers.log_user_unblocked_bot") as mock_unblock, \
         patch("handlers.log_bot_added_to_chat") as mock_add:
        await my_chat_member_handler(update, context)
        mock_unblock.assert_called_once()
        mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_my_chat_member_handler_skips_added_for_private_chat():
    """Handler skips 'Bot added to chat' for private chats (handled by /start)."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = 123456
    update.my_chat_member.chat.title = None
    update.my_chat_member.chat.type = "private"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "left"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "member"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "User"
    update.my_chat_member.from_user.username = "user"

    context = MagicMock()

    with patch("handlers.log_bot_added_to_chat") as mock_add, \
         patch("handlers.log_user_unblocked_bot") as mock_unblock:
        await my_chat_member_handler(update, context)
        mock_add.assert_not_called()
        mock_unblock.assert_not_called()


@pytest.mark.asyncio
async def test_my_chat_member_handler_still_logs_added_for_groups():
    """Handler still logs 'Bot added to chat' for group chats."""
    update = MagicMock()
    update.my_chat_member = MagicMock()
    update.my_chat_member.chat = MagicMock()
    update.my_chat_member.chat.id = -100789
    update.my_chat_member.chat.title = "Test Group"
    update.my_chat_member.chat.type = "supergroup"
    update.my_chat_member.old_chat_member = MagicMock()
    update.my_chat_member.old_chat_member.status = "left"
    update.my_chat_member.new_chat_member = MagicMock()
    update.my_chat_member.new_chat_member.status = "member"
    update.my_chat_member.from_user = MagicMock()
    update.my_chat_member.from_user.id = 123456
    update.my_chat_member.from_user.first_name = "Admin"
    update.my_chat_member.from_user.username = "admin"

    context = MagicMock()

    with patch("handlers.log_bot_added_to_chat") as mock_add, \
         patch("handlers.is_bot_admin", return_value=True):
        await my_chat_member_handler(update, context)
        mock_add.assert_called_once()


# --- gallery-dl domain whitelist tests ---


@pytest.mark.asyncio
async def test_handle_url_skips_unsupported_domain_not_in_whitelist(update, context):
    """URLs with domains not in gallery-dl whitelist are skipped entirely."""
    update.message.text = "https://github.com/user/repo"

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset()), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset(["pinterest.com", "reddit.com"])), \
         patch("handlers.extract_domain", return_value="github.com"), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock) as mock_fallback:
        await handle_url(update, context)

    # Should NOT call gallery-dl fallback for github.com
    mock_fallback.assert_not_called()
    # Should show error in P2P
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Unsupported" in text


@pytest.mark.asyncio
async def test_handle_url_passes_whitelisted_domain_to_gallery_dl(update, context):
    """URLs with domains in gallery-dl whitelist are passed to fallback."""
    update.message.text = "https://pinterest.com/pin/123/"

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset()), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset(["pinterest.com"])), \
         patch("handlers.extract_domain", return_value="pinterest.com"), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock, return_value=True) as mock_fallback:
        await handle_url(update, context)

    mock_fallback.assert_called_once()


@pytest.mark.asyncio
async def test_handle_url_skips_all_when_domain_list_empty(update, context):
    """When domain list is empty (generation failed), skip all gallery-dl fallback."""
    update.message.text = "https://pinterest.com/pin/123/"

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset()), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset()), \
         patch("handlers.extract_domain", return_value="pinterest.com"), \
         patch("handlers.handle_gallery_dl_fallback", new_callable=AsyncMock) as mock_fallback:
        await handle_url(update, context)

    mock_fallback.assert_not_called()
    # Should show error in P2P
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Unsupported" in text


# --- auth notification tracking tests ---


class TestHandlerAuth:
    @pytest.mark.asyncio
    async def test_handle_url_unauthorized_p2p_first_time(self):
        """Unauthorized user in P2P gets message once."""
        from auth import _already_told_users

        _already_told_users.clear()

        update = MagicMock()
        update.message.text = "https://youtube.com/watch?v=123"
        update.message.message_id = 1
        update.message.from_user = MagicMock()
        update.message.from_user.id = 999999
        update.message.chat = MagicMock()
        update.message.chat.type = "private"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch("handlers.is_authorized", return_value=False), \
             patch("handlers.is_group_chat", return_value=False), \
             patch("handlers.was_notified", return_value=False), \
             patch("handlers.mark_notified"):
            await handle_url(update, context)

            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args
            assert "not authorized" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_handle_url_unauthorized_p2p_second_time(self):
        """Unauthorized user in P2P silently ignored after first time."""
        from auth import _already_told_users

        _already_told_users.clear()

        update = MagicMock()
        update.message.text = "https://youtube.com/watch?v=123"
        update.message.message_id = 1
        update.message.from_user = MagicMock()
        update.message.from_user.id = 999999
        update.message.chat = MagicMock()
        update.message.chat.type = "private"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch("handlers.is_authorized", return_value=False), \
             patch("handlers.is_group_chat", return_value=False), \
             patch("handlers.was_notified", return_value=True):
            await handle_url(update, context)

            update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_command_unauthorized_p2p_first_time(self):
        """Unauthorized user /audio in P2P gets message once."""
        from auth import _already_told_users

        _already_told_users.clear()

        update = MagicMock()
        update.message.text = "/audio https://youtube.com/watch?v=123"
        update.message.message_id = 1
        update.message.from_user = MagicMock()
        update.message.from_user.id = 999999
        update.message.chat = MagicMock()
        update.message.chat.type = "private"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch("handlers.is_authorized", return_value=False), \
             patch("handlers.is_group_chat", return_value=False), \
             patch("handlers.was_notified", return_value=False), \
             patch("handlers.mark_notified"):
            await audio_command(update, context)

            update.message.reply_text.assert_called_once()
            call_args = update.message.reply_text.call_args
            assert "not authorized" in call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_audio_command_unauthorized_p2p_second_time(self):
        """Unauthorized user /audio in P2P silently ignored after first time."""
        from auth import _already_told_users

        _already_told_users.clear()

        update = MagicMock()
        update.message.text = "/audio https://youtube.com/watch?v=123"
        update.message.message_id = 1
        update.message.from_user = MagicMock()
        update.message.from_user.id = 999999
        update.message.chat = MagicMock()
        update.message.chat.type = "private"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch("handlers.is_authorized", return_value=False), \
             patch("handlers.is_group_chat", return_value=False), \
             patch("handlers.was_notified", return_value=True):
            await audio_command(update, context)

            update.message.reply_text.assert_not_called()

    # --- End-to-end notification tracking tests (real was_notified/mark_notified) ---

    @pytest.mark.asyncio
    async def test_handle_url_unauthorized_p2p_e2e_notifies_and_suppresses(self):
        """End-to-end: first call notifies, second call suppresses (real _already_told_users)."""
        from auth import _already_told_users

        _already_told_users.clear()

        def _make_update(user_id, chat_type="private"):
            u = MagicMock()
            u.message.text = "https://youtube.com/watch?v=123"
            u.message.message_id = 1
            u.message.from_user = MagicMock()
            u.message.from_user.id = user_id
            u.message.chat = MagicMock()
            u.message.chat.type = chat_type
            u.message.reply_text = AsyncMock()
            return u

        user_id = 777777

        with patch("auth.ALLOWED_USER_IDS", [111]), \
             patch("auth.ALLOWED_GROUP_IDS", []):
            # First request: should reply with "not authorized"
            u1 = _make_update(user_id)
            ctx1 = MagicMock()
            ctx1.user_data = {}
            await handle_url(u1, ctx1)
            u1.message.reply_text.assert_called_once()
            assert "not authorized" in u1.message.reply_text.call_args[0][0].lower()
            assert user_id in _already_told_users

            # Second request: should be silently suppressed
            u2 = _make_update(user_id)
            ctx2 = MagicMock()
            ctx2.user_data = {}
            await handle_url(u2, ctx2)
            u2.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_command_unauthorized_p2p_e2e_notifies_and_suppresses(self):
        """End-to-end: first /audio notifies, second suppresses (real _already_told_users)."""
        from auth import _already_told_users

        _already_told_users.clear()

        def _make_update(user_id, chat_type="private"):
            u = MagicMock()
            u.message.text = "/audio https://youtube.com/watch?v=123"
            u.message.message_id = 1
            u.message.from_user = MagicMock()
            u.message.from_user.id = user_id
            u.message.chat = MagicMock()
            u.message.chat.type = chat_type
            u.message.reply_text = AsyncMock()
            return u

        user_id = 888888

        with patch("auth.ALLOWED_USER_IDS", [111]), \
             patch("auth.ALLOWED_GROUP_IDS", []):
            # First request: should reply with "not authorized"
            u1 = _make_update(user_id)
            ctx1 = MagicMock()
            ctx1.user_data = {}
            await audio_command(u1, ctx1)
            u1.message.reply_text.assert_called_once()
            assert "not authorized" in u1.message.reply_text.call_args[0][0].lower()
            assert user_id in _already_told_users

            # Second request: should be silently suppressed
            u2 = _make_update(user_id)
            ctx2 = MagicMock()
            ctx2.user_data = {}
            await audio_command(u2, ctx2)
            u2.message.reply_text.assert_not_called()

    # --- Unauthorized user in group chat (silently ignored) ---

class TestMyChatMemberHandler:
    @pytest.mark.asyncio
    async def test_bot_added_by_admin(self):
        """Bot added by admin should stay and log."""
        from handlers import my_chat_member_handler

        update = MagicMock(spec=Update)
        update.my_chat_member = MagicMock(spec=ChatMemberUpdated)
        update.my_chat_member.chat = MagicMock(spec=Chat)
        update.my_chat_member.chat.type = "supergroup"
        update.my_chat_member.chat.id = 123456
        update.my_chat_member.old_chat_member = MagicMock()
        update.my_chat_member.old_chat_member.status = "left"
        update.my_chat_member.new_chat_member = MagicMock()
        update.my_chat_member.new_chat_member.status = "member"
        update.my_chat_member.from_user = MagicMock(spec=User)
        update.my_chat_member.from_user.id = 999999

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot.leave_chat = AsyncMock()

        with patch('handlers.is_bot_admin', return_value=True), \
             patch('handlers.log_bot_added_to_chat'):
            await my_chat_member_handler(update, context)

            context.bot.leave_chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_bot_added_by_non_admin(self):
        """Bot added by non-admin should leave."""
        from handlers import my_chat_member_handler

        update = MagicMock(spec=Update)
        update.my_chat_member = MagicMock(spec=ChatMemberUpdated)
        update.my_chat_member.chat = MagicMock(spec=Chat)
        update.my_chat_member.chat.type = "supergroup"
        update.my_chat_member.chat.id = 123456
        update.my_chat_member.chat.title = "Test Group"
        update.my_chat_member.old_chat_member = MagicMock()
        update.my_chat_member.old_chat_member.status = "left"
        update.my_chat_member.new_chat_member = MagicMock()
        update.my_chat_member.new_chat_member.status = "member"
        update.my_chat_member.from_user = MagicMock(spec=User)
        update.my_chat_member.from_user.id = 123456
        update.my_chat_member.from_user.first_name = "Test"
        update.message = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot.leave_chat = AsyncMock()
        context.bot.send_message = AsyncMock()

        with patch('handlers.is_bot_admin', return_value=False):
            await my_chat_member_handler(update, context)

            context.bot.leave_chat.assert_called_once_with(123456)
            context.bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_url_group_unauthorized_silent(self):
        """Unauthorized user in group chat is silently ignored (no reply, no notification).

        In groups, is_authorized always returns True (bot only exists if admin added it).
        But if is_authorized returns False AND is_group_chat returns True, the handler
        silently returns without replying or tracking notification state.
        """
        from auth import _already_told_users

        _already_told_users.clear()
        user_id = 555555

        update = MagicMock()
        update.message.text = "https://youtube.com/watch?v=123"
        update.message.message_id = 1
        update.message.from_user = MagicMock()
        update.message.from_user.id = user_id
        update.message.chat = MagicMock()
        update.message.chat.type = "group"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch("handlers.is_authorized", return_value=False), \
             patch("handlers.is_group_chat", return_value=True):
            await handle_url(update, context)

        # Should NOT reply at all
        update.message.reply_text.assert_not_called()
        # was_notified/mark_notified should NOT be called (group path skips notification tracking)
        # Verify the real _already_told_users was not affected
        assert user_id not in _already_told_users

    @pytest.mark.asyncio
    async def test_audio_command_group_unauthorized_silent(self):
        """Unauthorized user /audio in group chat is silently ignored."""
        from auth import _already_told_users

        _already_told_users.clear()
        user_id = 666666

        update = MagicMock()
        update.message.text = "/audio https://youtube.com/watch?v=123"
        update.message.message_id = 1
        update.message.from_user = MagicMock()
        update.message.from_user.id = user_id
        update.message.chat = MagicMock()
        update.message.chat.type = "group"
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {}

        with patch("handlers.is_authorized", return_value=False), \
             patch("handlers.is_group_chat", return_value=True):
            await audio_command(update, context)

        # Should NOT reply at all
        update.message.reply_text.assert_not_called()
        # Verify the real _already_told_users was not affected
        assert user_id not in _already_told_users


@pytest.mark.asyncio
async def test_handle_url_ignores_unauthorized_reply_to_bot_in_group():
    """Unauthorized user replying to bot message in a group is silently ignored."""
    update = MagicMock()
    update.message.text = "https://youtube.com/watch?v=abc"
    update.message.message_id = 42
    update.message.from_user.id = 99999
    update.message.chat.type = "group"
    update.message.chat.id = 100
    update.effective_chat = update.message.chat
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.from_user = MagicMock()
    update.message.reply_to_message.from_user.is_bot = True
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot_data = {"bot_username": "testbot"}
    context.user_data = {}

    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers._is_allowed", return_value=False):
        await handle_url(update, context)
        update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_handle_url_ytdlp_supported_site(update, context):
    """handle_url processes yt-dlp supported sites (non-yt/tt/ig) via generic download."""
    update.message.text = "https://www.dailymotion.com/video/x7tgfd"
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset(["dailymotion.com"])), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset()), \
         patch("handlers.detect_platform", return_value=None), \
         patch("handlers.get_metadata", return_value={"title": "Test Video"}), \
         patch("handlers.download_video", return_value=True), \
         patch("handlers.cleanup_file"), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024*1024), \
         patch("builtins.open", MagicMock()):
        update.message.reply_video = AsyncMock()
        await handle_url(update, context)
        update.message.reply_video.assert_called_once()


@pytest.mark.asyncio
async def test_handle_url_unsupported_site(update, context):
    """handle_url shows 'Unsupported platform' for sites not in any domain list."""
    update.message.text = "https://unknown-site.com/video"
    with patch("handlers.is_authorized", return_value=True), \
         patch("handlers.get_ytdlp_domains", return_value=frozenset()), \
         patch("handlers.get_gallery_dl_domains", return_value=frozenset()), \
         patch("handlers.detect_platform", return_value=None):
        await handle_url(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert text == "Unsupported platform"
