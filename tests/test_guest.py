"""Unit tests for the guest module — InlineQueryResult builders and GuestModePoller."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from guest import (
    GuestModePoller,
    _text_result,
    _video_result,
    _photo_result,
    _media_group_result,
)


# ---------------------------------------------------------------------------
# InlineQueryResult helpers — pure functions
# ---------------------------------------------------------------------------


class TestTextResult:
    """Tests for _text_result()."""

    def test_returns_article_type(self):
        result = _text_result("hello world")
        assert result["type"] == "article"

    def test_has_string_id(self):
        result = _text_result("hello")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_title_truncated_to_64_chars(self):
        long_text = "a" * 200
        result = _text_result(long_text)
        assert len(result["title"]) == 64
        assert result["title"] == "a" * 64

    def test_title_short_text_not_truncated(self):
        result = _text_result("short")
        assert result["title"] == "short"

    def test_input_message_content_has_text(self):
        result = _text_result("download this")
        assert result["input_message_content"]["message_text"] == "download this"

    def test_full_message_text_not_truncated(self):
        """message_text should keep the original text even if title is truncated."""
        long_text = "b" * 200
        result = _text_result(long_text)
        assert result["input_message_content"]["message_text"] == long_text


class TestVideoResult:
    """Tests for _video_result()."""

    def test_returns_video_type(self):
        result = _video_result("abc123")
        assert result["type"] == "video"

    def test_has_string_id(self):
        result = _video_result("abc123")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_video_file_id(self):
        result = _video_result("my_file_id")
        assert result["video_file_id"] == "my_file_id"

    def test_default_title(self):
        result = _video_result("abc")
        assert result["title"] == "Video"

    def test_custom_title(self):
        result = _video_result("abc", title="My Video")
        assert result["title"] == "My Video"

    def test_thumbnail_included_when_provided(self):
        result = _video_result("abc", thumbnail_url="https://example.com/thumb.jpg")
        assert result["thumb_url"] == "https://example.com/thumb.jpg"

    def test_thumbnail_omitted_when_empty(self):
        result = _video_result("abc", thumbnail_url="")
        assert "thumb_url" not in result


class TestPhotoResult:
    """Tests for _photo_result()."""

    def test_returns_photo_type(self):
        result = _photo_result("file123")
        assert result["type"] == "photo"

    def test_has_string_id(self):
        result = _photo_result("file123")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_photo_file_id(self):
        result = _photo_result("photo_id")
        assert result["photo_file_id"] == "photo_id"


class TestMediaGroupResult:
    """Tests for _media_group_result()."""

    def test_single_file_returns_photo_result(self):
        result = _media_group_result(["file_1"])
        assert result["type"] == "photo"
        assert result["photo_file_id"] == "file_1"

    def test_multiple_files_returns_first_photo(self):
        result = _media_group_result(["first", "second", "third"])
        assert result["type"] == "photo"
        assert result["photo_file_id"] == "first"

    def test_empty_list_returns_text_result(self):
        result = _media_group_result([])
        assert result["type"] == "article"
        assert "No images found" in result["input_message_content"]["message_text"]


# ---------------------------------------------------------------------------
# GuestModePoller — auth and URL extraction
# ---------------------------------------------------------------------------


def _make_guest_message(text, caller_id=999, reply_to=None):
    """Build a minimal raw_update dict with a guest_message."""
    msg = {
        "guest_message": {
            "text": text,
            "guest_query_id": "gq_12345",
            "guest_bot_caller_user": {
                "id": caller_id,
                "first_name": "Guest",
                "username": "guest_user",
            },
        }
    }
    if reply_to is not None:
        msg["guest_message"]["reply_to_message"] = {
            "text": reply_to,
        }
    return msg


@pytest.fixture
def poller():
    """Create a GuestModePoller with a mock client."""
    mock_app = MagicMock()
    mock_app.bot = MagicMock()
    poller = GuestModePoller(bot_token="test:token", application=mock_app)
    poller._client = AsyncMock()
    return poller


class TestHandleGuestMessageAuth:
    """Tests for auth checks in _handle_guest_message."""

    @pytest.mark.asyncio
    async def test_unauthorized_user_silently_ignored(self, poller):
        """Unauthorized user gets no answer_guest_query call."""
        with patch("guest.is_user_allowed", return_value=False):
            await poller._handle_guest_message(_make_guest_message("https://youtube.com/watch?v=abc", caller_id=999))

        poller._client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_urls_in_message_replies_with_please_include_url(self, poller):
        """No URLs in the tag message should reply with 'Please include a URL'."""
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=[]):
            await poller._handle_guest_message(_make_guest_message("check this out"))

        poller._client.post.assert_called_once()
        call_kwargs = poller._client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["guest_query_id"] == "gq_12345"
        result = json.loads(payload["result"])
        assert result["type"] == "article"
        assert "Please include a URL" in result["input_message_content"]["message_text"]

    @pytest.mark.asyncio
    async def test_url_from_tag_message_is_extracted(self, poller):
        """URL in the guest message text is used for download."""
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=["https://youtube.com/watch?v=abc"]), \
             patch.object(poller, "_download_and_build_result", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = _video_result("file_id", title="Test Video")
            await poller._handle_guest_message(
                _make_guest_message("https://youtube.com/watch?v=abc")
            )

        mock_download.assert_called_once_with("https://youtube.com/watch?v=abc", "youtube", "gq_12345")

    @pytest.mark.asyncio
    async def test_url_from_replied_to_message_used_when_tag_has_none(self, poller):
        """When tag has no URL, the replied-to message URL is used."""
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls") as mock_extract, \
             patch.object(poller, "_download_and_build_result", new_callable=AsyncMock) as mock_download:
            # First call (tag text) returns empty; second call (replied-to text) returns URL
            mock_extract.side_effect = [[], ["https://tiktok.com/@user/video/123"]]
            mock_download.return_value = _video_result("file_id", title="TikTok video")
            await poller._handle_guest_message(
                _make_guest_message("try this", reply_to="https://tiktok.com/@user/video/123")
            )

        mock_download.assert_called_once_with("https://tiktok.com/@user/video/123", "tiktok", "gq_12345")

    @pytest.mark.asyncio
    async def test_unsupported_platform_returns_error_text(self, poller):
        """Unsupported platform returns a text result with error."""
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=["https://unknown.com/page"]), \
             patch("guest.detect_platform", return_value=None):
            await poller._handle_guest_message(
                _make_guest_message("https://unknown.com/page")
            )

        poller._client.post.assert_called_once()
        call_kwargs = poller._client.post.call_args
        payload = call_kwargs[1]["json"]
        result = json.loads(payload["result"])
        assert result["type"] == "article"
        assert "Unsupported platform" in result["input_message_content"]["message_text"]

    @pytest.mark.asyncio
    async def test_answer_guest_query_called_with_result(self, poller):
        """The answerGuestQuery API call is made with correct query_id and result."""
        fake_result = {"type": "video", "id": "abc", "video_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=["https://example.com/v"]), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch.object(poller, "_download_and_build_result", new_callable=AsyncMock, return_value=fake_result) as mock_download, \
             patch.object(poller, "answer_guest_query", new_callable=AsyncMock) as mock_answer:
            await poller._handle_guest_message(
                _make_guest_message("https://example.com/v")
            )

        mock_answer.assert_called_once_with("gq_12345", fake_result)
