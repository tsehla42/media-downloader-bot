"""Tests for platforms.tiktok module: handle_tiktok."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.tiktok import handle_tiktok


def _make_typing_indicator_mock():
    """Create a mock that behaves as typing_indicator (async context manager factory)."""
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=mock_cm)


@pytest.fixture
def update():
    u = MagicMock()
    u.message = MagicMock()
    u.message.message_id = 42
    u.message.from_user = MagicMock()
    u.message.from_user.id = 123456
    return u


@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.user_data = {}
    return ctx


# --- handle_tiktok tests ---


@pytest.mark.asyncio
async def test_handle_tiktok_sends_single_photo(update, context):
    """handle_tiktok sends a single photo and returns True."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, return_value=500000), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        result = await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    assert result is True
    assert context.user_data["_content_type"] == "image"
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_handle_tiktok_sends_multiple_photos(update, context):
    """handle_tiktok sends multiple photos and returns True."""
    images = ["/tmp/tt1.jpg", "/tmp/tt2.jpg", "/tmp/tt3.jpg"]
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=images), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, return_value=1500000), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        result = await handle_tiktok(update, context, "https://tiktok.com/@user/gallery/456")

    assert result is True
    assert context.user_data["_content_type"] == "image"
    assert context.user_data["_file_size_mb"] == round(1500000 / (1024 * 1024), 2)
    assert context.user_data["_request_success"] is True


@pytest.mark.asyncio
async def test_handle_tiktok_returns_false_when_gallery_dl_fails(update, context):
    """handle_tiktok returns False when gallery-dl returns no images."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=[]), \
         patch("platforms.tiktok.send_images") as mock_send, \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        result = await handle_tiktok(update, context, "https://tiktok.com/@user/photo/789")

    assert result is False
    mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_handle_tiktok_cleans_up_on_success(update, context):
    """handle_tiktok cleans up output directory even on success."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, return_value=500000), \
         patch("platforms.tiktok.cleanup_dir") as mock_cleanup, \
         patch("platforms.tiktok.cleanup_file"):
        await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    mock_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_handle_tiktok_cleans_up_on_failure(update, context):
    """handle_tiktok cleans up output directory when gallery-dl fails."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=[]), \
         patch("platforms.tiktok.send_images"), \
         patch("platforms.tiktok.cleanup_dir") as mock_cleanup, \
         patch("platforms.tiktok.cleanup_file"):
        await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    mock_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_handle_tiktok_cleans_up_on_exception(update, context):
    """handle_tiktok cleans up output directory even when send_images raises."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, side_effect=Exception("send failed")), \
         patch("platforms.tiktok.cleanup_dir") as mock_cleanup, \
         patch("platforms.tiktok.cleanup_file"):
        with pytest.raises(Exception, match="send failed"):
            await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    mock_cleanup.assert_called_once()


@pytest.mark.asyncio
async def test_handle_tiktok_passes_empty_cookies(update, context):
    """handle_tiktok passes empty string for cookies (no auth needed)."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=[]) as mock_dl, \
         patch("platforms.tiktok.send_images"), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    mock_dl.assert_called_once()
    args = mock_dl.call_args
    assert args[0][2] == ""  # cookies parameter


@pytest.mark.asyncio
async def test_handle_tiktok_sets_file_size_mb(update, context):
    """handle_tiktok calculates file_size_mb correctly from total image size."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, return_value=2 * 1024 * 1024), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    assert context.user_data["_file_size_mb"] == 2.0


@pytest.mark.asyncio
async def test_handle_tiktok_zero_size_images(update, context):
    """handle_tiktok sets file_size_mb to None when total size is 0."""
    with patch("platforms.tiktok.download_video", return_value=False), \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, return_value=0), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    assert context.user_data["_file_size_mb"] is None


# --- Metadata-failure path tests (from handlers._download_and_send) ---


@pytest.mark.asyncio
async def test_download_and_send_tiktok_delegates_to_handle_tiktok():
    """_download_and_send delegates TikTok directly to handle_tiktok (no metadata fetch)."""
    from handlers import _download_and_send

    update = MagicMock()
    update.message.message_id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("handlers.handle_tiktok", new_callable=AsyncMock, return_value=True) as mock_handle:
        await _download_and_send(update, context, "https://tiktok.com/@user/video/123")

    mock_handle.assert_called_once()
    # Should NOT show error message since handle_tiktok succeeded
    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_download_and_send_tiktok_handle_fails_shows_error():
    """When handle_tiktok returns False, show error message to user."""
    from handlers import _download_and_send

    update = MagicMock()
    update.message.message_id = 42
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}

    with patch("handlers.detect_platform", return_value="tiktok"), \
         patch("handlers.handle_tiktok", new_callable=AsyncMock, return_value=False):
        await _download_and_send(update, context, "https://tiktok.com/@user/video/123")

    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Could not fetch post" in text


# --- Metadata check tests ---


@pytest.mark.asyncio
async def test_handle_tiktok_skips_video_for_photo_post(update, context):
    """handle_tiktok skips video download when metadata indicates photo post."""
    metadata = {"ext": "jpg", "title": "photo post"}

    with patch("platforms.tiktok.get_metadata", return_value=metadata), \
         patch("platforms.tiktok.download_video") as mock_video, \
         patch("platforms.tiktok.download_gallery_dl_images", return_value=["/tmp/tt.jpg"]), \
         patch("platforms.tiktok.send_images", new_callable=AsyncMock, return_value=500000), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        result = await handle_tiktok(update, context, "https://tiktok.com/@user/photo/123")

    assert result is True
    mock_video.assert_not_called()
    assert context.user_data["_content_type"] == "image"


@pytest.mark.asyncio
async def test_handle_tiktok_tries_video_when_metadata_fails(update, context):
    """handle_tiktok falls back to video download when metadata fetch fails."""
    update.message.reply_video = AsyncMock()
    with patch("platforms.tiktok.get_metadata", return_value=None), \
         patch("platforms.tiktok.download_video", return_value=True), \
         patch("platforms.tiktok.os.path.isfile", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        result = await handle_tiktok(update, context, "https://tiktok.com/@user/video/123")

    assert result is True
    assert context.user_data["_content_type"] == "video"


@pytest.mark.asyncio
async def test_handle_tiktok_tries_video_for_unknown_ext(update, context):
    """handle_tiktok tries video download when metadata ext is not a known image format."""
    metadata = {"ext": "mp4", "title": "video post"}
    update.message.reply_video = AsyncMock()

    with patch("platforms.tiktok.get_metadata", return_value=metadata), \
         patch("platforms.tiktok.download_video", return_value=True), \
         patch("platforms.tiktok.os.path.isfile", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.tiktok.cleanup_dir"), \
         patch("platforms.tiktok.cleanup_file"):
        result = await handle_tiktok(update, context, "https://tiktok.com/@user/video/123")

    assert result is True
    assert context.user_data["_content_type"] == "video"
