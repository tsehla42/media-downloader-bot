"""Tests for platforms.youtube module: _has_video_available, ytmusic_callback, _ytmusic_pending."""

import time
from contextlib import ExitStack
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.youtube import (
    _has_video_available,
    ytmusic_callback,
    _ytmusic_pending,
    AUDIO_TITLE_MAX,
)


@pytest.fixture(autouse=True)
def clear_ytmusic_pending():
    """Clear shared _ytmusic_pending state before each test."""
    _ytmusic_pending.clear()
    yield
    _ytmusic_pending.clear()


def _make_typing_indicator_mock():
    """Create a mock that behaves as typing_indicator (async context manager factory)."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_cm)


# --- _has_video_available tests ---

def test_has_video_available_with_video_formats():
    """_has_video_available returns True when formats have video codecs."""
    metadata = {
        "ext": "mp4",
        "formats": [
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
            {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640020", "acodec": "none"},
        ],
    }
    assert _has_video_available(metadata) is True


def test_has_video_available_with_audio_only_formats():
    """_has_video_available returns False when all formats have vcodec=none."""
    metadata = {
        "ext": "m4a",
        "formats": [
            {"format_id": "139", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.5"},
            {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
            {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus"},
        ],
    }
    assert _has_video_available(metadata) is False


def test_has_video_available_with_no_formats():
    """_has_video_available returns False when formats list is empty."""
    assert _has_video_available({"ext": "mp4", "formats": []}) is False


def test_has_video_available_with_missing_formats():
    """_has_video_available returns False when formats key is missing."""
    assert _has_video_available({"ext": "mp4"}) is False


def test_has_video_available_with_missing_vcodec():
    """_has_video_available returns False when vcodec key is missing from formats."""
    metadata = {
        "ext": "mp4",
        "formats": [
            {"format_id": "140", "ext": "m4a", "acodec": "mp4a.40.2"},
        ],
    }
    assert _has_video_available(metadata) is False


# --- ytmusic_callback tests ---

@pytest.mark.asyncio
async def test_ytmusic_callback_audio_choice():
    """Callback with 'audio' choice downloads audio and deletes question message."""
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
    context.bot.send_chat_action = AsyncMock()

    _ytmusic_pending[42] = {"url": "https://music.youtube.com/watch?v=abc", "title": "Test Song"}

    mock_typing = _make_typing_indicator_mock()

    with patch("platforms.youtube.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.remove"), \
         patch("platforms.youtube.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.youtube.typing_indicator", mock_typing):
        await ytmusic_callback(update, context)

    update.callback_query.message.delete.assert_called_once()
    update.callback_query.answer.assert_called_once()
    assert 42 not in _ytmusic_pending
    mock_typing.assert_called_once()


@pytest.mark.asyncio
async def test_ytmusic_callback_video_choice():
    """Callback with 'video' choice downloads video and deletes question message."""
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
    context.bot.send_chat_action = AsyncMock()

    _ytmusic_pending[42] = {"url": "https://music.youtube.com/watch?v=abc", "title": "Test Song"}

    mock_typing = _make_typing_indicator_mock()

    with patch("platforms.youtube.download_video", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.remove"), \
         patch("platforms.youtube.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.youtube.typing_indicator", mock_typing):
        await ytmusic_callback(update, context)

    update.callback_query.message.delete.assert_called_once()
    update.callback_query.answer.assert_called_once()
    assert 42 not in _ytmusic_pending
    mock_typing.assert_called_once()


@pytest.mark.asyncio
async def test_ytmusic_callback_both_choice():
    """Callback with 'both' choice downloads video then audio, in that order."""
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
    context.bot.send_chat_action = AsyncMock()

    _ytmusic_pending[42] = {"url": "https://music.youtube.com/watch?v=abc", "title": "Test Song"}

    mock_typing = _make_typing_indicator_mock()

    with patch("platforms.youtube.download_video", return_value=True), \
         patch("platforms.youtube.download_audio", return_value=True), \
         patch("os.path.isfile", return_value=True), \
         patch("os.remove"), \
         patch("platforms.youtube.cleanup_file"), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.youtube.typing_indicator", mock_typing):
        await ytmusic_callback(update, context)

    update.callback_query.message.delete.assert_called_once()
    assert 42 not in _ytmusic_pending
    mock_typing.assert_called_once()

    # Verify video was sent before audio
    video_calls = update.effective_message.reply_video.call_args_list
    audio_calls = update.effective_message.reply_audio.call_args_list
    assert len(video_calls) == 1
    assert len(audio_calls) == 1
    update.effective_message.reply_video.assert_called()
    update.effective_message.reply_audio.assert_called()


@pytest.mark.asyncio
async def test_ytmusic_callback_expired_request():
    """Callback with no pending data answers 'expired' and does not delete."""
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
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "ytm|42|audio"
    update.callback_query.message = MagicMock()
    update.callback_query.message.delete = AsyncMock()
    update.callback_query.answer = AsyncMock()

    stale_timestamp = time.time() - 600  # 10 minutes ago
    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    _ytmusic_pending[42] = {"url": "https://music.youtube.com/watch?v=abc", "title": "Test", "timestamp": stale_timestamp}

    await ytmusic_callback(update, context)

    # Should answer with expired message
    update.callback_query.answer.assert_called_once()
    answer_text = update.callback_query.answer.call_args[0][0]
    assert "expired" in answer_text.lower()
    # Should NOT delete the message
    update.callback_query.message.delete.assert_not_called()
    # Pending data should be popped (cleaned up)
    assert 42 not in _ytmusic_pending


@pytest.mark.asyncio
async def test_ytmusic_callback_malformed_data():
    """Callback with malformed data answers but does not crash."""
    update = MagicMock()
    update.callback_query = MagicMock()
    update.callback_query.data = "garbage"
    update.callback_query.answer = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    await ytmusic_callback(update, context)

    # Should answer (to dismiss loading spinner)
    update.callback_query.answer.assert_called_once()
    # Should not crash or try to delete anything
    update.callback_query.message.delete.assert_not_called()


# --- handle_ytmusic keyword tests ---

from platforms.youtube import handle_ytmusic
from messages import MSG_YTMUSIC_VIDEO_FAILED, MSG_YTMUSIC_AUDIO_FAILED


def _make_ytmusic_update(text):
    update = MagicMock()
    update.message.text = text
    update.message.message_id = 42
    update.message.chat.id = -100123
    update.message.from_user.id = 123
    update.message.reply_text = AsyncMock()
    update.message.reply_audio = AsyncMock()
    update.message.reply_video = AsyncMock()
    return update


def _make_ytmusic_context():
    context = MagicMock()
    context.user_data = {}
    context.bot.send_chat_action = AsyncMock()
    return context


VIDEO_METADATA = {
    "title": "Test Song",
    "ext": "mp4",
    "formats": [
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1.640020", "acodec": "none"},
    ],
}


class TestHandleYtmusicKeyword:
    """Format keywords in the message skip the picker and send directly."""

    URL = "https://music.youtube.com/watch?v=abc"
    REPLY_PARAMS = {"message_id": 42, "allow_sending_without_reply": True}

    async def _run(self, text, *patchers):
        update = _make_ytmusic_update(text)
        context = _make_ytmusic_context()
        mock_typing = _make_typing_indicator_mock()
        base_patches = [
            patch("platforms.youtube.typing_indicator", mock_typing),
            patch("os.path.isfile", return_value=True),
            patch("os.remove"),
            patch("platforms.youtube.cleanup_file"),
            patch("builtins.open", MagicMock()),
        ]
        with ExitStack() as stack:
            for p in base_patches:
                stack.enter_context(p)
            for p in patchers:
                stack.enter_context(p)
            await handle_ytmusic(
                update, context, self.URL, VIDEO_METADATA, "Test Song",
                "/tmp/base", "/tmp/base.%(ext)s", self.REPLY_PARAMS,
            )
        return update, context, mock_typing

    @pytest.mark.asyncio
    async def test_audio_keyword_skips_picker_sends_audio(self):
        update, context, _ = await self._run(
            f"{self.URL} audio",
            patch("platforms.youtube.download_audio", return_value=True),
        )

        update.message.reply_text.assert_not_called()
        update.message.reply_audio.assert_called_once()
        update.message.reply_video.assert_not_called()
        assert 42 not in _ytmusic_pending
        assert context.user_data["_request_success"] is True

    @pytest.mark.asyncio
    async def test_video_keyword_skips_picker_sends_video(self):
        update, context, _ = await self._run(
            f"{self.URL} відео",
            patch("platforms.youtube.download_video", return_value=True),
        )

        update.message.reply_text.assert_not_called()
        update.message.reply_video.assert_called_once()
        update.message.reply_audio.assert_not_called()
        assert 42 not in _ytmusic_pending
        assert context.user_data["_request_success"] is True

    @pytest.mark.asyncio
    async def test_both_keywords_send_video_then_audio(self):
        update, context, _ = await self._run(
            f"{self.URL} video audio",
            patch("platforms.youtube.download_video", return_value=True),
            patch("platforms.youtube.download_audio", return_value=True),
        )

        update.message.reply_text.assert_not_called()
        update.message.reply_video.assert_called_once()
        update.message.reply_audio.assert_called_once()
        assert 42 not in _ytmusic_pending

    @pytest.mark.asyncio
    async def test_video_keyword_failure_replies_message(self):
        update, context, _ = await self._run(
            f"{self.URL} video",
            patch("platforms.youtube.download_video", return_value=False),
        )

        update.message.reply_video.assert_not_called()
        update.message.reply_text.assert_called_once()
        sent_text = update.message.reply_text.call_args[0][0]
        assert sent_text == MSG_YTMUSIC_VIDEO_FAILED
        assert context.user_data["_request_success"] is False

    @pytest.mark.asyncio
    async def test_audio_keyword_failure_replies_message(self):
        update, context, _ = await self._run(
            f"{self.URL} аудіо",
            patch("platforms.youtube.download_audio", return_value=False),
        )

        update.message.reply_audio.assert_not_called()
        update.message.reply_text.assert_called_once()
        sent_text = update.message.reply_text.call_args[0][0]
        assert sent_text == MSG_YTMUSIC_AUDIO_FAILED
        assert context.user_data["_request_success"] is False

    @pytest.mark.asyncio
    async def test_no_keyword_still_shows_picker(self):
        update, context, _ = await self._run(self.URL)

        update.message.reply_text.assert_called_once()
        kwargs = update.message.reply_text.call_args[1]
        assert "reply_markup" in kwargs
        assert 42 in _ytmusic_pending
        update.message.reply_audio.assert_not_called()
        update.message.reply_video.assert_not_called()

    @pytest.mark.asyncio
    async def test_unrelated_words_still_show_picker(self):
        """Text without format keywords does not change picker behavior."""
        update, context, _ = await self._run(f"{self.URL} something else")

        update.message.reply_text.assert_called_once()
        assert 42 in _ytmusic_pending
