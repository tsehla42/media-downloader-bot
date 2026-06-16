"""Unit tests for the guest module — InlineQueryResult builders and handle_guest."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# InlineQueryResult helpers — pure functions
# ---------------------------------------------------------------------------


class TestTextResult:
    """Tests for _text_result()."""

    def test_returns_article_type(self):
        from guest import _text_result
        result = _text_result("hello world")
        assert result["type"] == "article"

    def test_has_string_id(self):
        from guest import _text_result
        result = _text_result("hello")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_title_truncated_to_100_chars(self):
        from guest import _text_result
        long_text = "a" * 200
        result = _text_result(long_text)
        assert len(result["title"]) == 100
        assert result["title"] == "a" * 100

    def test_title_short_text_not_truncated(self):
        from guest import _text_result
        result = _text_result("short")
        assert result["title"] == "short"

    def test_input_message_content_has_text(self):
        from guest import _text_result
        result = _text_result("download this")
        assert result["input_message_content"]["message_text"] == "download this"

    def test_full_message_text_not_truncated(self):
        """message_text should keep the original text even if title is truncated."""
        from guest import _text_result
        long_text = "b" * 200
        result = _text_result(long_text)
        assert result["input_message_content"]["message_text"] == long_text


class TestVideoResult:
    """Tests for _video_result() — returns raw dict with video_file_id."""

    def test_returns_dict(self):
        from guest import _video_result
        result = _video_result("abc123")
        assert isinstance(result, dict)

    def test_type_is_video(self):
        from guest import _video_result
        result = _video_result("abc123")
        assert result["type"] == "video"

    def test_has_string_id(self):
        from guest import _video_result
        result = _video_result("abc123")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_video_file_id(self):
        from guest import _video_result
        result = _video_result("my_file_id")
        assert result["video_file_id"] == "my_file_id"

    def test_default_title(self):
        from guest import _video_result
        result = _video_result("abc")
        assert result["title"] == "Video"

    def test_custom_title(self):
        from guest import _video_result
        result = _video_result("abc", title="My Video")
        assert result["title"] == "My Video"

    def test_title_truncated_to_100(self):
        from guest import _video_result
        result = _video_result("abc", title="x" * 200)
        assert len(result["title"]) == 100

    def test_thumbnail_included_when_provided(self):
        from guest import _video_result
        result = _video_result("abc", thumbnail_url="https://example.com/thumb.jpg")
        assert result["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_default_thumbnail_when_empty(self):
        from guest import _video_result
        result = _video_result("abc", thumbnail_url="")
        assert result["thumbnail_url"] == ""


class TestPhotoResult:
    """Tests for _photo_result() — returns raw dict with photo_file_id."""

    def test_returns_dict(self):
        from guest import _photo_result
        result = _photo_result("file123")
        assert isinstance(result, dict)

    def test_type_is_photo(self):
        from guest import _photo_result
        result = _photo_result("file123")
        assert result["type"] == "photo"

    def test_has_string_id(self):
        from guest import _photo_result
        result = _photo_result("file123")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_photo_file_id(self):
        from guest import _photo_result
        result = _photo_result("photo_id")
        assert result["photo_file_id"] == "photo_id"


class TestMediaGroupResult:
    """Tests for _media_group_result()."""

    def test_single_file_returns_photo_result(self):
        from guest import _media_group_result
        result = _media_group_result(["file_1"])
        assert result["type"] == "photo"
        assert result["photo_file_id"] == "file_1"

    def test_multiple_files_returns_first_photo(self):
        from guest import _media_group_result
        result = _media_group_result(["first", "second", "third"])
        assert result["type"] == "photo"
        assert result["photo_file_id"] == "first"

    def test_empty_list_returns_text_result(self):
        from guest import _media_group_result
        result = _media_group_result([])
        assert result["type"] == "article"
        assert "No images found" in result["input_message_content"]["message_text"]


# ---------------------------------------------------------------------------
# handle_guest — standalone handler tests
# ---------------------------------------------------------------------------


def _make_guest_message(text="https://youtube.com/watch?v=123",
                        caller_id=12345, reply_to=None, guest_query_id="q1"):
    """Build a mock guest message object."""
    msg = MagicMock()
    msg.text = text
    msg.guest_query_id = guest_query_id
    msg.from_user = MagicMock()
    msg.from_user.id = caller_id
    msg.from_user.first_name = "Test"
    msg.from_user.username = "testuser"
    msg.reply_to_message = reply_to
    return msg


def _make_update(guest_message):
    """Build a mock Update with guest_message."""
    update = MagicMock()
    update.guest_message = guest_message
    return update


def _make_context():
    """Build a mock Context with answer_guest_query."""
    context = MagicMock()
    context.bot.answer_guest_query = AsyncMock()
    return context


class TestHandleGuestAuth:
    """Tests for auth checks in handle_guest."""

    @pytest.mark.asyncio
    async def test_unauthorized_first_call_sends_message(self):
        """First unauthorized guest call sends unauth message."""
        from guest import handle_guest
        from auth import _already_told_guest_users
        _already_told_guest_users.clear()

        msg = _make_guest_message(caller_id=99999)
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=False), \
             patch("guest.was_notified_guest", return_value=False), \
             patch("guest.mark_notified_guest"), \
             patch("guest.log_unauthorized_access"):
            await handle_guest(update, context)
            context.bot.answer_guest_query.assert_called_once()
            call_args = context.bot.answer_guest_query.call_args
            result = call_args[1]["result"]
            assert "not authorized" in result["input_message_content"]["message_text"].lower()

    @pytest.mark.asyncio
    async def test_unauthorized_second_call_silent(self):
        """Second unauthorized guest call is silently ignored."""
        from guest import handle_guest
        msg = _make_guest_message(caller_id=99999)
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=False), \
             patch("guest.was_notified_guest", return_value=True), \
             patch("guest.log_unauthorized_access"):
            await handle_guest(update, context)
            context.bot.answer_guest_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_unauthorized_calls_log_unauthorized_access(self):
        """Unauthorized guest calls log to service.jsonl via log_unauthorized_access."""
        from guest import handle_guest
        mock_log = MagicMock()

        msg = _make_guest_message(caller_id=99999)
        msg.chat = MagicMock()
        msg.chat.id = 99999
        msg.chat.type = "private"
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=False), \
             patch("guest.was_notified_guest", return_value=True), \
             patch("guest.log_unauthorized_access", mock_log):
            await handle_guest(update, context)
            mock_log.assert_called_once()
            args = mock_log.call_args[0]
            assert args[0].id == 99999  # caller
            assert args[2] == "guest"   # command

    @pytest.mark.asyncio
    async def test_no_urls_replies_with_hint(self):
        """Tag without URL and without reply shows hint."""
        from guest import handle_guest
        msg = _make_guest_message(text="hello bot")
        msg.reply_to_message = None
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=[]):
            await handle_guest(update, context)
            context.bot.answer_guest_query.assert_called_once()
            call_args = context.bot.answer_guest_query.call_args
            result = call_args[1]["result"]
            assert "URL" in result["input_message_content"]["message_text"]

    @pytest.mark.asyncio
    async def test_reply_to_bot_without_url_silent(self):
        """Reply to bot guest message without URL is silently ignored."""
        from guest import handle_guest
        reply_msg = MagicMock()
        reply_msg.text = "nice video"
        reply_msg.from_user = MagicMock()
        reply_msg.from_user.id = 111
        reply_msg.from_user.is_bot = True
        msg = _make_guest_message(text="@botname", reply_to=reply_msg)
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=[]):
            await handle_guest(update, context)
            context.bot.answer_guest_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_url_from_replied_message(self):
        from guest import handle_guest
        reply_msg = MagicMock()
        reply_msg.text = "https://tiktok.com/@user/video/123"
        msg = _make_guest_message(text="@botname get this", reply_to=reply_msg)
        update = _make_update(msg)
        context = _make_context()

        fake_result = {"type": "article", "id": "1", "title": "ok",
                       "input_message_content": {"message_text": "ok"}}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls") as mock_extract, \
             patch("guest.detect_platform", return_value="tiktok"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock) as mock_dl:
            mock_extract.side_effect = [[], ["https://tiktok.com/@user/video/123"]]
            mock_dl.return_value = (fake_result, "video", 1.5)
            await handle_guest(update, context)
            mock_dl.assert_called_once()
            assert "tiktok.com" in mock_dl.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unsupported_platform(self):
        from guest import handle_guest
        msg = _make_guest_message(text="https://example.com/page")
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value=None), \
             patch("guest.get_gallery_dl_domains", return_value=frozenset({"deviantart.com"})):
            await handle_guest(update, context)
            context.bot.answer_guest_query.assert_called_once()
            result = context.bot.answer_guest_query.call_args[1]["result"]
            assert "Unsupported" in result["input_message_content"]["message_text"]

    @pytest.mark.asyncio
    async def test_gallery_dl_domain_tries_fallback(self):
        """Gallery-dl supported domains should try fallback, not show 'Unsupported'."""
        from guest import handle_guest
        msg = _make_guest_message(text="https://www.deviantart.com/art/123")
        update = _make_update(msg)
        context = _make_context()

        fake_result = {"type": "photo", "id": "abc", "photo_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value=None), \
             patch("guest.get_gallery_dl_domains", return_value=frozenset({"deviantart.com"})), \
             patch("guest._gallery_dl_result", new_callable=AsyncMock, return_value=(fake_result, "image", 0.5)):
            await handle_guest(update, context)
            context.bot.answer_guest_query.assert_called_once()
            result = context.bot.answer_guest_query.call_args[1]["result"]
            assert result["type"] == "photo"

    @pytest.mark.asyncio
    async def test_answer_guest_query_called_with_result(self):
        from guest import handle_guest
        msg = _make_guest_message(text="https://youtube.com/watch?v=abc")
        update = _make_update(msg)
        context = _make_context()

        fake_result = {"type": "video", "id": "abc", "video_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock, return_value=(fake_result, "video", 2.5)):
            await handle_guest(update, context)

        context.bot.answer_guest_query.assert_called_once_with(
            "q1", result=fake_result
        )

    @pytest.mark.asyncio
    async def test_download_error_replies_with_error(self):
        from guest import handle_guest
        msg = _make_guest_message(text="https://youtube.com/watch?v=abc")
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock, side_effect=Exception("boom")):
            await handle_guest(update, context)

        context.bot.answer_guest_query.assert_called_once()
        result = context.bot.answer_guest_query.call_args[1]["result"]
        assert "Download failed" in result["input_message_content"]["message_text"]
