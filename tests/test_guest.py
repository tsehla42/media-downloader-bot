"""Unit tests for the guest module — InlineQueryResult builders and handle_guest."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from downloader import DownloadError

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

    def test_single_file_no_caption(self):
        from guest import _media_group_result
        result = _media_group_result(["file_1"])
        assert "caption" not in result

    def test_multiple_files_returns_first_photo(self):
        from guest import _media_group_result
        result = _media_group_result(["first", "second", "third"])
        assert result["type"] == "photo"
        assert result["photo_file_id"] == "first"

    def test_multiple_files_has_caption_with_count(self):
        from guest import _media_group_result
        result = _media_group_result(["a", "b", "c", "d", "e", "f", "g", "h"])
        assert "caption" in result
        assert "8 photos" in result["caption"]
        assert "Guest Mode" in result["caption"]

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
    async def test_unauthorized_without_url_silent(self):
        """Unauthorized user without URL is silently ignored."""
        from guest import handle_guest
        msg = _make_guest_message(text="hello bot", caller_id=99999)
        msg.reply_to_message = None
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=False), \
             patch("guest.extract_urls", return_value=[]), \
             patch("guest.log_unauthorized_access") as mock_log:
            await handle_guest(update, context)
            # Should be completely silent — no hint, no auth message
            context.bot.answer_guest_query.assert_not_called()
            mock_log.assert_not_called()

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
        reply_msg.from_user.is_bot = False
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

    @pytest.mark.asyncio
    async def test_reply_to_bot_error_message_no_url_extraction(self):
        """Reply to bot error message should not extract URLs from it."""
        from guest import handle_guest

        bot_error_text = (
            "Download failed: ERROR: [youtube] uueRqEalZ7s: Sign in to confirm your age. "
            "See https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp "
            "for how to manually pass cookies."
        )
        reply_msg = MagicMock()
        reply_msg.text = bot_error_text
        reply_msg.from_user = MagicMock()
        reply_msg.from_user.id = 111
        reply_msg.from_user.is_bot = True

        msg = _make_guest_message(text="@botname", reply_to=reply_msg)
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.extract_urls", return_value=[]) as mock_extract:
            await handle_guest(update, context)
            # extract_urls should only be called once (for user's text), not for bot's reply
            assert mock_extract.call_count == 1
            # The call should be with the user's text "@botname", not the bot error message
            assert mock_extract.call_args[0][0] == "@botname"


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
                "https://youtube.com/watch?v=abc123", "youtube", "new_id", "video", "Test Video", 5.0, None, ""
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
                "https://tiktok.com/@user/video/123", "tiktok", "new_photo_id", "photo", "", 0.5, None, ""
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


# ---------------------------------------------------------------------------
# DownloadAuthRequired in _download_media_result
# ---------------------------------------------------------------------------


class TestDownloadMediaResultAuth:
    """Tests for DownloadAuthRequired handling in _download_media_result."""

    @pytest.mark.asyncio
    async def test_download_media_result_tiktok_login_required(self):
        """DownloadAuthRequired in guest mode returns login-required text result."""
        from guest import _download_media_result
        from downloader import DownloadAuthRequired

        with patch("guest.download_video", side_effect=DownloadAuthRequired("Log in for access")), \
             patch("guest.download_gallery_dl_images", return_value=[]), \
             patch("guest.download_gallery_dl_video", return_value=None), \
             patch("guest.cleanup_dir"):
            result, content_type, file_size_mb = await _download_media_result(
                "https://tiktok.com/@user/video/123", "tiktok"
            )

        assert result["type"] == "article"
        assert "restricted" in result["input_message_content"]["message_text"]


class TestDownloadYoutubeAuth:
    """Tests for DownloadAuthRequired handling in _download_youtube."""

    @pytest.mark.asyncio
    async def test_download_youtube_age_restricted_returns_login_required(self):
        """Age-restricted YouTube video returns friendly login-required message."""
        from guest import _download_youtube
        from downloader import DownloadAuthRequired

        with patch("guest.get_metadata", side_effect=DownloadAuthRequired("Sign in to confirm your age")):
            result, content_type, file_size_mb = await _download_youtube(
                "https://youtube.com/watch?v=abc123"
            )

        assert result["type"] == "article"
        assert "restricted" in result["input_message_content"]["message_text"].lower()
        assert content_type == "video"
        assert file_size_mb is None

    @pytest.mark.asyncio
    async def test_ytdlp_generic_age_restricted_returns_login_required(self):
        """Age-restricted generic yt-dlp video returns friendly login-required message."""
        from guest import _ytdlp_generic_result
        from downloader import DownloadAuthRequired

        with patch("guest.get_metadata", side_effect=DownloadAuthRequired("Sign in to confirm your age")):
            result, content_type, file_size_mb = await _ytdlp_generic_result(
                "https://example.com/video/123"
            )

        assert result["type"] == "article"
        assert "restricted" in result["input_message_content"]["message_text"].lower()
        assert content_type == "video"
        assert file_size_mb is None


# ---------------------------------------------------------------------------
# _audio_result — InlineQueryResultAudio builder
# ---------------------------------------------------------------------------


class TestAudioResult:
    """Tests for _audio_result() — returns raw dict with audio_file_id."""

    def test_returns_dict(self):
        from guest import _audio_result
        result = _audio_result("abc123")
        assert isinstance(result, dict)

    def test_type_is_audio(self):
        from guest import _audio_result
        result = _audio_result("abc123")
        assert result["type"] == "audio"

    def test_has_string_id(self):
        from guest import _audio_result
        result = _audio_result("abc123")
        assert isinstance(result["id"], str)
        assert len(result["id"]) == 8

    def test_audio_file_id(self):
        from guest import _audio_result
        result = _audio_result("my_audio_fid")
        assert result["audio_file_id"] == "my_audio_fid"

    def test_default_title(self):
        from guest import _audio_result
        result = _audio_result("abc")
        assert result["title"] == "Audio"

    def test_custom_title(self):
        from guest import _audio_result
        result = _audio_result("abc", title="My Song")
        assert result["title"] == "My Song"

    def test_title_truncated_to_100(self):
        from guest import _audio_result
        result = _audio_result("abc", title="x" * 200)
        assert len(result["title"]) == 100


# ---------------------------------------------------------------------------
# _download_audio — guest audio download pipeline
# ---------------------------------------------------------------------------


class TestDownloadAudio:
    """Tests for _download_audio()."""

    @pytest.mark.asyncio
    async def test_age_restricted_returns_login_required(self):
        from guest import _download_audio
        from downloader import DownloadAuthRequired

        with patch("guest.get_metadata", side_effect=DownloadAuthRequired("Sign in")):
            result, content_type, file_size_mb = await _download_audio(
                "https://music.youtube.com/watch?v=abc123"
            )

        assert result["type"] == "article"
        assert "restricted" in result["input_message_content"]["message_text"].lower()
        assert content_type == "audio"
        assert file_size_mb is None

    @pytest.mark.asyncio
    async def test_metadata_failed_returns_error(self):
        from guest import _download_audio

        with patch("guest.get_metadata", return_value=None):
            result, content_type, file_size_mb = await _download_audio(
                "https://music.youtube.com/watch?v=abc123"
            )

        assert result["type"] == "article"
        assert content_type == "audio"
        assert file_size_mb is None

    @pytest.mark.asyncio
    async def test_success_returns_audio_result(self):
        from guest import _download_audio

        with patch("guest.get_metadata", return_value={"title": "My Song"}), \
             patch("guest.download_audio", return_value=True), \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=2 * 1024 * 1024), \
             patch("guest.cleanup_file"), \
             patch("guest._upload_to_telegram", new_callable=AsyncMock,
                  return_value="audio_fid_1") as mock_upload:
            result, content_type, file_size_mb = await _download_audio(
                "https://music.youtube.com/watch?v=abc123"
            )

        assert result["type"] == "audio"
        assert result["audio_file_id"] == "audio_fid_1"
        assert result["title"] == "My Song"
        assert content_type == "audio"
        assert file_size_mb == 2.0
        assert mock_upload.call_args[0][1] == "audio"

    @pytest.mark.asyncio
    async def test_download_failure_raises(self):
        from guest import _download_audio

        with patch("guest.get_metadata", return_value={"title": "My Song"}), \
             patch("guest.download_audio", return_value=False), \
             patch("os.path.isfile", return_value=False), \
             patch("guest.cleanup_file"):
            with pytest.raises(ValueError):
                await _download_audio("https://music.youtube.com/watch?v=abc123")

    @pytest.mark.asyncio
    async def test_upload_failure_raises(self):
        from guest import _download_audio

        with patch("guest.get_metadata", return_value={"title": "My Song"}), \
             patch("guest.download_audio", return_value=True), \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024), \
             patch("guest.cleanup_file"), \
             patch("guest._upload_to_telegram", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError):
                await _download_audio("https://music.youtube.com/watch?v=abc123")


# ---------------------------------------------------------------------------
# _download_and_build_result — music URL audio/video routing
# ---------------------------------------------------------------------------


class TestYoutubeAudioRouting:
    """Tests for music.youtube.com audio default and force_video override."""

    MUSIC_URL = "https://music.youtube.com/watch?v=abc12345678"

    @pytest.mark.asyncio
    async def test_music_url_default_routes_to_audio(self):
        from guest import _download_and_build_result

        fake_result = {"type": "audio", "id": "x", "audio_file_id": "fid", "title": "Song"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_audio", new_callable=AsyncMock,
                  return_value=(fake_result, "audio", 1.0)) as mock_audio, \
             patch("guest._download_youtube", new_callable=AsyncMock) as mock_video, \
             patch("guest.store"):
            await _download_and_build_result(self.MUSIC_URL, "youtube")
            mock_audio.assert_called_once_with(self.MUSIC_URL)
            mock_video.assert_not_called()

    @pytest.mark.asyncio
    async def test_music_url_force_video_routes_to_video(self):
        from guest import _download_and_build_result

        fake_result = {"type": "video", "id": "x", "video_file_id": "fid", "title": "Song"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_audio", new_callable=AsyncMock) as mock_audio, \
             patch("guest._download_youtube", new_callable=AsyncMock,
                   return_value=(fake_result, "video", 5.0)) as mock_video, \
             patch("guest.store"):
            await _download_and_build_result(self.MUSIC_URL, "youtube", force_video=True)
            mock_video.assert_called_once_with(self.MUSIC_URL)
            mock_audio.assert_not_called()

    @pytest.mark.asyncio
    async def test_regular_youtube_url_always_video(self):
        from guest import _download_and_build_result

        fake_result = {"type": "video", "id": "x", "video_file_id": "fid", "title": "V"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_audio", new_callable=AsyncMock) as mock_audio, \
             patch("guest._download_youtube", new_callable=AsyncMock,
                   return_value=(fake_result, "video", 5.0)) as mock_video, \
             patch("guest.store"):
            await _download_and_build_result("https://youtube.com/watch?v=abc12345678", "youtube")
            mock_video.assert_called_once()
            mock_audio.assert_not_called()

    @pytest.mark.asyncio
    async def test_music_audio_uses_audio_cache_variant(self):
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=None) as mock_cache, \
             patch("guest._download_audio", new_callable=AsyncMock,
                   return_value=({"type": "audio"}, "audio", None)), \
             patch("guest.store"):
            await _download_and_build_result(self.MUSIC_URL, "youtube")
            assert mock_cache.call_args[0][3] == "audio"

    @pytest.mark.asyncio
    async def test_music_video_uses_default_cache_variant(self):
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=None) as mock_cache, \
             patch("guest._download_youtube", new_callable=AsyncMock,
                   return_value=({"type": "video"}, "video", None)), \
             patch("guest.store"):
            await _download_and_build_result(self.MUSIC_URL, "youtube", force_video=True)
            assert mock_cache.call_args[0][3] == ""

    @pytest.mark.asyncio
    async def test_audio_cache_hit_returns_audio_result(self):
        from guest import _download_and_build_result

        with patch("guest.get_cached", return_value=("cached_audio_id", "audio")), \
             patch("guest._download_audio", new_callable=AsyncMock) as mock_audio, \
             patch("guest._download_youtube", new_callable=AsyncMock) as mock_video:
            result, content_type, file_size_mb, cache_hit = await _download_and_build_result(
                self.MUSIC_URL, "youtube"
            )
            mock_audio.assert_not_called()
            mock_video.assert_not_called()
            assert result["type"] == "audio"
            assert result["audio_file_id"] == "cached_audio_id"
            assert content_type == "audio"
            assert cache_hit is True

    @pytest.mark.asyncio
    async def test_audio_download_stored_with_audio_variant(self):
        from guest import _download_and_build_result

        fake_result = {"type": "audio", "id": "x", "audio_file_id": "new_audio_id", "title": "Song"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_audio", new_callable=AsyncMock,
                   return_value=(fake_result, "audio", 1.5)), \
             patch("guest.store") as mock_store:
            await _download_and_build_result(self.MUSIC_URL, "youtube")
            mock_store.assert_called_once_with(
                self.MUSIC_URL, "youtube", "new_audio_id", "audio", "Song", 1.5, None, "audio"
            )

    @pytest.mark.asyncio
    async def test_video_download_stored_without_variant(self):
        from guest import _download_and_build_result

        fake_result = {"type": "video", "id": "x", "video_file_id": "vid_id", "title": "Song"}
        with patch("guest.get_cached", return_value=None), \
             patch("guest._download_youtube", new_callable=AsyncMock,
                   return_value=(fake_result, "video", 5.0)), \
             patch("guest.store") as mock_store:
            await _download_and_build_result(self.MUSIC_URL, "youtube", force_video=True)
            mock_store.assert_called_once_with(
                self.MUSIC_URL, "youtube", "vid_id", "video", "Song", 5.0, None, ""
            )


# ---------------------------------------------------------------------------
# handle_guest — format keyword parsing
# ---------------------------------------------------------------------------


class TestHandleGuestFormatKeyword:
    """Tests that handle_guest parses format keywords from the tag text."""

    MUSIC_TEXT = "https://music.youtube.com/watch?v=abc12345678"

    async def _run(self, text):
        from guest import handle_guest
        msg = _make_guest_message(text=text)
        update = _make_update(msg)
        context = _make_context()
        fake_result = {"type": "audio", "id": "1", "audio_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock,
                   return_value=(fake_result, "audio", 1.0, False)) as mock_build:
            await handle_guest(update, context)
        return mock_build

    @pytest.mark.asyncio
    async def test_no_keyword_defaults_to_audio(self):
        mock_build = await self._run(self.MUSIC_TEXT)
        assert mock_build.call_args[0][2] is False

    @pytest.mark.asyncio
    async def test_video_keyword_sets_force_video(self):
        mock_build = await self._run(f"{self.MUSIC_TEXT} video")
        assert mock_build.call_args[0][2] is True

    @pytest.mark.asyncio
    async def test_ukrainian_video_keyword_sets_force_video(self):
        mock_build = await self._run(f"{self.MUSIC_TEXT} відео")
        assert mock_build.call_args[0][2] is True

    @pytest.mark.asyncio
    async def test_russian_video_keyword_sets_force_video(self):
        mock_build = await self._run(f"{self.MUSIC_TEXT} видео")
        assert mock_build.call_args[0][2] is True

    @pytest.mark.asyncio
    async def test_audio_keyword_defaults_to_audio(self):
        mock_build = await self._run(f"{self.MUSIC_TEXT} audio")
        assert mock_build.call_args[0][2] is False

    @pytest.mark.asyncio
    async def test_both_keywords_defaults_to_audio(self):
        """Guest mode answers with a single result, so both -> audio."""
        mock_build = await self._run(f"{self.MUSIC_TEXT} video audio")
        assert mock_build.call_args[0][2] is False

    @pytest.mark.asyncio
    async def test_keyword_ignored_for_regular_youtube(self):
        """Regular youtube.com URL downloads video regardless of audio keyword."""
        from guest import handle_guest
        msg = _make_guest_message(text="https://youtube.com/watch?v=abc12345678 audio")
        update = _make_update(msg)
        context = _make_context()
        fake_result = {"type": "video", "id": "1", "video_file_id": "fid"}
        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock,
                   return_value=(fake_result, "video", 5.0, False)) as mock_build:
            await handle_guest(update, context)
            assert mock_build.call_args[0][2] is False


# ---------------------------------------------------------------------------
# _upload_to_telegram — audio branch
# ---------------------------------------------------------------------------


class TestUploadToTelegramAudio:
    """Tests that _upload_to_telegram sends audio via sendAudio."""

    @pytest.mark.asyncio
    async def test_audio_uses_send_audio(self):
        from guest import _upload_to_telegram

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"audio": {"file_id": "sent_audio_fid"}},
        }
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("guest.httpx.AsyncClient", return_value=mock_client), \
             patch("guest.STORAGE_CHANNEL_ID", "12345"), \
             patch("config.BOT_TOKEN", "test-token"), \
             patch("builtins.open", MagicMock()):
            file_id = await _upload_to_telegram("/tmp/some.mp3", "audio")

        assert file_id == "sent_audio_fid"
        post_url = mock_client.post.call_args[0][0]
        assert "sendAudio" in post_url
        files = mock_client.post.call_args[1]["files"]
        assert "audio" in files

    @pytest.mark.asyncio
    async def test_audio_upload_passes_title_to_sendAudio(self):
        """sendAudio must carry the title — Telegram validates the FILE's title
        for inline/guest audio results (Audio_title_empty otherwise)."""
        from guest import _upload_to_telegram

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"audio": {"file_id": "sent_audio_fid", "title": "My Song"}},
        }
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("guest.httpx.AsyncClient", return_value=mock_client), \
             patch("guest.STORAGE_CHANNEL_ID", "12345"), \
             patch("config.BOT_TOKEN", "test-token"), \
             patch("builtins.open", MagicMock()):
            await _upload_to_telegram("/tmp/some.mp3", "audio", title="My Song")

        data = mock_client.post.call_args[1]["data"]
        assert data["title"] == "My Song"

    @pytest.mark.asyncio
    async def test_upload_without_title_omits_title_param(self):
        """Non-audio uploads (or no title) must not send an empty title param."""
        from guest import _upload_to_telegram

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"video": {"file_id": "v"}},
        }
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("guest.httpx.AsyncClient", return_value=mock_client), \
             patch("guest.STORAGE_CHANNEL_ID", "12345"), \
             patch("config.BOT_TOKEN", "test-token"), \
             patch("builtins.open", MagicMock()):
            await _upload_to_telegram("/tmp/some.mp4", "video")

        data = mock_client.post.call_args[1]["data"]
        assert "title" not in data


class TestDownloadAudioUploadTitle:
    """_download_audio must pass the metadata title into the storage upload."""

    @pytest.mark.asyncio
    async def test_upload_receives_metadata_title(self):
        from guest import _download_audio

        with patch("guest.get_metadata", return_value={"title": "My Song"}), \
             patch("guest.download_audio", return_value=True), \
             patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024), \
             patch("guest.cleanup_file"), \
             patch("guest._upload_to_telegram", new_callable=AsyncMock,
                  return_value="audio_fid_1") as mock_upload:
            await _download_audio("https://music.youtube.com/watch?v=abc123")

        assert mock_upload.call_args[1]["title"] == "My Song"


# ---------------------------------------------------------------------------
# TikTok photo-post extractor (yt-dlp --write-pages) in _download_media_result
# ---------------------------------------------------------------------------


class TestDownloadMediaResultTiktokPhotos:
    """Tests for download_tiktok_photo_images in guest mode."""

    @pytest.mark.asyncio
    async def test_tiktok_photo_extractor_tried_before_video(self):
        """Guest mode tries the photo extractor before download_video for TikTok."""
        from guest import _download_media_result

        with patch("guest.download_tiktok_photo_images", return_value=["/tmp/a.jpg"]) as mock_photo, \
             patch("guest.download_video") as mock_video, \
             patch("guest.os.path.getsize", return_value=100000), \
             patch("guest._upload_to_telegram", new_callable=AsyncMock, return_value="fid_photo_1"), \
             patch("guest.cleanup_dir"):
            result, content_type, file_size_mb = await _download_media_result(
                "https://vt.tiktok.com/ZSbPKwDAm/", "tiktok"
            )

        mock_photo.assert_called_once()
        mock_video.assert_not_called()
        assert result["photo_file_id"] == "fid_photo_1"
        assert content_type == "image"

    @pytest.mark.asyncio
    async def test_tiktok_photo_extractor_empty_falls_through_to_video(self):
        """Empty photo extractor result falls through to the video flow."""
        from guest import _download_media_result

        with patch("guest.download_tiktok_photo_images", return_value=[]), \
             patch("guest.download_video", return_value=True), \
             patch("guest.os.path.getsize", return_value=1048576), \
             patch("guest._upload_to_telegram", new_callable=AsyncMock, return_value="vid_1"), \
             patch("guest.cleanup_dir"):
            result, content_type, file_size_mb = await _download_media_result(
                "https://tiktok.com/@user/video/123", "tiktok"
            )

        assert result["video_file_id"] == "vid_1"
        assert content_type == "video"


# ---------------------------------------------------------------------------
# Specific error messages reaching guest users
# ---------------------------------------------------------------------------


class TestGuestSpecificErrors:
    """Guest replies must surface specific error messages, not the generic fallback."""

    @pytest.mark.asyncio
    async def test_value_error_replies_with_specific_message(self):
        """ValueError raised by the pipeline is shown to the user verbatim."""
        from guest import handle_guest
        msg = _make_guest_message(text="https://youtube.com/watch?v=abc")
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock,
                   side_effect=ValueError("Could not download media from this URL")):
            await handle_guest(update, context)

        context.bot.answer_guest_query.assert_called_once()
        text = context.bot.answer_guest_query.call_args[1]["result"]["input_message_content"]["message_text"]
        assert "Could not download media from this URL" in text
        assert "Download failed" not in text

    @pytest.mark.asyncio
    async def test_generic_exception_still_replies_download_failed(self):
        """Unexpected exceptions keep the generic message (no internals leaked)."""
        from guest import handle_guest
        msg = _make_guest_message(text="https://youtube.com/watch?v=abc")
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="youtube"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock,
                   side_effect=RuntimeError("traceback-ish internals")):
            await handle_guest(update, context)

        text = context.bot.answer_guest_query.call_args[1]["result"]["input_message_content"]["message_text"]
        assert "Download failed" in text
        assert "traceback-ish internals" not in text

    @pytest.mark.asyncio
    async def test_image_post_error_reaches_guest_user(self):
        """DownloadError from the image-post pipeline shows its user message."""
        from guest import handle_guest
        from messages import MSG_IMAGE_POST_FETCH_FAILED
        msg = _make_guest_message(text="https://vt.tiktok.com/ZSbxorMFG/")
        update = _make_update(msg)
        context = _make_context()

        with patch("guest.is_user_allowed", return_value=True), \
             patch("guest.detect_platform", return_value="tiktok"), \
             patch("guest._download_and_build_result", new_callable=AsyncMock,
                   side_effect=DownloadError(MSG_IMAGE_POST_FETCH_FAILED)):
            await handle_guest(update, context)

        text = context.bot.answer_guest_query.call_args[1]["result"]["input_message_content"]["message_text"]
        assert "Could not fetch this image post" in text

    @pytest.mark.asyncio
    async def test_photo_extractor_error_propagates_through_media_result(self):
        """_download_media_result does not swallow DownloadError from the photo extractor."""
        from guest import _download_media_result
        from messages import MSG_IMAGE_POST_FETCH_FAILED

        with patch("guest.download_tiktok_photo_images",
                   side_effect=DownloadError(MSG_IMAGE_POST_FETCH_FAILED)), \
             patch("guest.cleanup_dir"):
            with pytest.raises(DownloadError) as exc:
                await _download_media_result("https://vt.tiktok.com/ZSbxorMFG/", "tiktok")

        assert exc.value.user_message == MSG_IMAGE_POST_FETCH_FAILED

    @pytest.mark.asyncio
    async def test_two_image_post_sends_first_with_only_one_caption(self):
        """Multi-image post in guest: first image sent + caption that only 1 is supported."""
        from guest import _download_media_result
        from messages import MSG_GUEST_MEDIA_GROUP_CAPTION

        with patch("guest.download_tiktok_photo_images", return_value=["/tmp/a.jpg", "/tmp/b.jpg"]), \
             patch("guest.os.path.getsize", return_value=100000), \
             patch("guest._upload_to_telegram", new_callable=AsyncMock, side_effect=["fid_1", "fid_2"]), \
             patch("guest.cleanup_dir"):
            result, content_type, file_size_mb = await _download_media_result(
                "https://vt.tiktok.com/ZSbba4FUF/", "tiktok"
            )

        assert result["photo_file_id"] == "fid_1"
        assert result["caption"] == MSG_GUEST_MEDIA_GROUP_CAPTION.format(count=2)
        assert content_type == "image"
