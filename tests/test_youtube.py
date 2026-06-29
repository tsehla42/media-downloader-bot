"""Tests for platforms.youtube module: _has_video_available, ytmusic_callback, _ytmusic_pending."""

import time
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
