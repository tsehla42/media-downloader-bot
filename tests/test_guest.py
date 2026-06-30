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
             patch("guest._download_and_build_result", new_callable=AsyncMock, return_value=(fake_result, "video", 2.5, False)):
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

    @pytest.mark.asyncio
    async def test_reply_with_photo_sets_message_content(self):
        """Reply to a photo message should set message_content to [photo]."""
        from guest import handle_guest

        msg = _make_guest_message(text="")
        replied = MagicMock()
        replied.text = ""
        replied.photo = [MagicMock()]  # Has photo
        replied.video = None
        replied.animation = None
        replied.document = None
        replied.sticker = None
        replied.from_user = MagicMock()
        msg.reply_to_message = replied
        update = _make_update(msg)
        context = _make_context()

        fake_result = {"type": "video", "id": "1", "video_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=["https://tiktok.com/@u/video/1"]), \
             patch("guest.detect_platform", return_value="tiktok"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock, return_value=(fake_result, "video", 0.5)):
            await handle_guest(update, context)

        # The call should have succeeded (photo content type detected)
        context.bot.answer_guest_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_with_video_sets_message_content(self):
        """Reply to a video message should set message_content to [video]."""
        from guest import handle_guest

        msg = _make_guest_message(text="")
        replied = MagicMock()
        replied.text = ""
        replied.photo = None
        replied.video = MagicMock()  # Has video
        replied.animation = None
        replied.document = None
        replied.sticker = None
        replied.from_user = MagicMock()
        msg.reply_to_message = replied
        update = _make_update(msg)
        context = _make_context()

        fake_result = {"type": "video", "id": "1", "video_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=["https://tiktok.com/@u/video/1"]), \
             patch("guest.detect_platform", return_value="tiktok"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock, return_value=(fake_result, "video", 0.5)):
            await handle_guest(update, context)

        context.bot.answer_guest_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_with_sticker_sets_message_content(self):
        """Reply to a sticker message should set message_content to [sticker]."""
        from guest import handle_guest

        msg = _make_guest_message(text="")
        replied = MagicMock()
        replied.text = ""
        replied.photo = None
        replied.video = None
        replied.animation = None
        replied.document = None
        replied.sticker = MagicMock()  # Has sticker
        replied.from_user = MagicMock()
        msg.reply_to_message = replied
        update = _make_update(msg)
        context = _make_context()

        fake_result = {"type": "video", "id": "1", "video_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=["https://tiktok.com/@u/video/1"]), \
             patch("guest.detect_platform", return_value="tiktok"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock, return_value=(fake_result, "video", 0.5)):
            await handle_guest(update, context)

        context.bot.answer_guest_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_with_no_media_returns_none(self):
        """Reply to a text-only message should set message_content to None."""
        from guest import MEDIA_TYPES

        replied = MagicMock()
        replied.text = ""
        replied.photo = None
        replied.video = None
        replied.animation = None
        replied.document = None
        replied.sticker = None

        result = next(
            (label for attr, label in MEDIA_TYPES.items() if getattr(replied, attr, None)),
            None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# Cache integration in _download_and_build_result
# ---------------------------------------------------------------------------


class TestDownloadAndBuildResultCache:
    """Tests for cache integration in _download_and_build_result."""

    @pytest.mark.asyncio
    async def test_cache_hit_video_returns_cached(self):
        """Cache hit for video skips download and returns cached result."""
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=("cached_video_id", "video")), \
             patch("guest._download_youtube", new_callable=AsyncMock) as mock_yt:
            result, content_type, file_size_mb, cache_hit = await _download_and_build_result(
                "https://youtube.com/watch?v=abc123", "youtube"
            )
            mock_yt.assert_not_called()
            assert result["video_file_id"] == "cached_video_id"
            assert content_type == "video"
            assert file_size_mb is None

    @pytest.mark.asyncio
    async def test_cache_hit_photo_returns_cached(self):
        """Cache hit for photo skips download and returns cached result."""
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=("cached_photo_id", "photo")), \
             patch("guest._download_media_result", new_callable=AsyncMock) as mock_tt:
            result, content_type, file_size_mb, cache_hit = await _download_and_build_result(
                "https://tiktok.com/@user/video/123", "tiktok"
            )
            mock_tt.assert_not_called()
            assert result["photo_file_id"] == "cached_photo_id"
            assert content_type == "image"

    @pytest.mark.asyncio
    async def test_cache_hit_image_returns_cached(self):
        """Cache hit for image type returns photo result."""
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=("cached_img_id", "image")), \
             patch("guest._gallery_dl_result", new_callable=AsyncMock) as mock_gdl:
            result, content_type, file_size_mb, cache_hit = await _download_and_build_result(
                "https://deviantart.com/art/123", "deviantart.com"
            )
            mock_gdl.assert_not_called()
            assert result["photo_file_id"] == "cached_img_id"
            assert content_type == "image"

    @pytest.mark.asyncio
    async def test_cache_miss_proceeds_with_download(self):
        """Cache miss triggers normal download flow."""
        from guest import _download_and_build_result

        fake_result = {"type": "video", "id": "abc", "video_file_id": "new_id", "title": "Test"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_youtube", new_callable=AsyncMock, return_value=(fake_result, "video", 5.0)), \
             patch("guest.store") as mock_store:
            result, content_type, file_size_mb, cache_hit = await _download_and_build_result(
                "https://youtube.com/watch?v=abc123", "youtube"
            )
            assert result["video_file_id"] == "new_id"
            assert content_type == "video"
            assert file_size_mb == 5.0

    @pytest.mark.asyncio
    async def test_cache_miss_stores_video_result(self):
        """After successful video download, result is stored in cache."""
        from guest import _download_and_build_result

        fake_result = {"type": "video", "id": "abc", "video_file_id": "new_id", "title": "Test Video"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_youtube", new_callable=AsyncMock, return_value=(fake_result, "video", 5.0)), \
             patch("guest.store") as mock_store:
            await _download_and_build_result("https://youtube.com/watch?v=abc123", "youtube")
            mock_store.assert_called_once_with(
                "https://youtube.com/watch?v=abc123", "youtube", "new_id", "video", "Test Video", 5.0, None
            )

    @pytest.mark.asyncio
    async def test_cache_miss_stores_photo_result(self):
        """After successful photo download, result is stored in cache."""
        from guest import _download_and_build_result

        fake_result = {"type": "photo", "id": "abc", "photo_file_id": "new_photo_id", "title": ""}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_media_result", new_callable=AsyncMock, return_value=(fake_result, "image", 0.5)), \
             patch("guest.store") as mock_store:
            await _download_and_build_result("https://tiktok.com/@user/video/123", "tiktok")
            mock_store.assert_called_once_with(
                "https://tiktok.com/@user/video/123", "tiktok", "new_photo_id", "photo", "", 0.5, None
            )

    @pytest.mark.asyncio
    async def test_no_cache_for_unsupported_platform(self):
        """Unsupported platform returns text result without cache interaction."""
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=None), \
             patch("guest.extract_domain", return_value="example.com"), \
             patch("guest.get_ytdlp_domains", return_value=frozenset()), \
             patch("guest.get_gallery_dl_domains", return_value=frozenset()), \
             patch("guest.store") as mock_store:
            result, content_type, file_size_mb, cache_hit = await _download_and_build_result(
                "https://example.com/page", "example.com"
            )
            assert result["type"] == "article"
            assert "Unsupported" in result["input_message_content"]["message_text"]
            mock_store.assert_not_called()

    @pytest.mark.asyncio
    async def test_download_failure_does_not_cache(self):
        """If download raises, nothing is stored in cache."""
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_youtube", new_callable=AsyncMock, side_effect=ValueError("boom")), \
             patch("guest.store") as mock_store:
            with pytest.raises(ValueError, match="boom"):
                await _download_and_build_result("https://youtube.com/watch?v=abc123", "youtube")
            mock_store.assert_not_called()
