"""Tests for platforms.instagram module: handle_instagram."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from platforms.instagram import handle_instagram
from downloader import DownloadAuthRequired


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


@pytest.mark.asyncio
async def test_handle_instagram_stories_without_cookies_returns_false(update, context):
    """Stories URL without cookies file returns False early."""
    with patch("platforms.instagram.IG_COOKIES_PATH", "ig-cookies.txt"), \
         patch("platforms.instagram.os.path.isfile", return_value=False):
        result = await handle_instagram(
            update, context,
            "https://www.instagram.com/stories/whhiteblood/3933848826919684824",
        )

    assert result is False


@pytest.mark.asyncio
async def test_handle_instagram_stories_with_cookies_proceeds(update, context):
    """Stories URL with cookies file proceeds to download."""
    update.message.reply_video = AsyncMock()

    def is_file(path):
        if path == "/path/to/cookies.txt":
            return True
        return path.endswith(".mp4")

    with patch("platforms.instagram.IG_COOKIES_PATH", "/path/to/cookies.txt"), \
         patch("platforms.instagram.os.path.isfile", side_effect=is_file), \
         patch("platforms.instagram.download_video", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.instagram.cleanup_video_files"):
        result = await handle_instagram(
            update, context,
            "https://www.instagram.com/stories/whhiteblood/3933848826919684824",
        )

    assert result is True


@pytest.mark.asyncio
async def test_handle_instagram_non_stories_without_cookies_proceeds(update, context):
    """Non-stories URL proceeds even when cookies file doesn't exist."""
    update.message.reply_video = AsyncMock()

    with patch("platforms.instagram.download_video", return_value=True), \
         patch("platforms.instagram.os.path.isfile", side_effect=lambda p: p.endswith(".mp4")), \
         patch("builtins.open", MagicMock()), \
         patch("platforms.instagram.cleanup_video_files"):
        result = await handle_instagram(
            update, context,
            "https://www.instagram.com/reel/DUruRXWChNQ",
        )

    assert result is True


@pytest.mark.asyncio
async def test_handle_instagram_stories_with_utm_params(update, context):
    """Stories URL with UTM params is correctly detected as stories."""
    with patch("platforms.instagram.IG_COOKIES_PATH", "ig-cookies.txt"), \
         patch("platforms.instagram.os.path.isfile", return_value=False):
        result = await handle_instagram(
            update, context,
            "https://www.instagram.com/stories/whhiteblood/3933848826919684824?utm_source=ig_story_item_share&igsh=abc",
        )

    assert result is False


@pytest.mark.asyncio
async def test_handle_instagram_download_auth_required_propagates(update, context):
    """DownloadAuthRequired from download_video propagates to caller."""
    with patch("platforms.instagram.download_video", side_effect=DownloadAuthRequired("content restricted")), \
         patch("platforms.instagram.cleanup_video_files"):
        with pytest.raises(DownloadAuthRequired):
            await handle_instagram(
                update, context,
                "https://www.instagram.com/reel/DUruRXWChNQ",
            )
