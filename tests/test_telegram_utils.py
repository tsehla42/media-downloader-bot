import io
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

from telegram.constants import ChatAction
from telegram_utils import typing_indicator, send_images


# ---------------------------------------------------------------------------
# typing_indicator tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_typing_indicator_sends_chat_action_immediately():
    """typing_indicator sends send_chat_action on entry."""
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    chat_id = 123456

    async with typing_indicator(chat_id, bot):
        # Right after entering, the initial send_chat_action should have been called
        bot.send_chat_action.assert_awaited_once_with(
            chat_id=chat_id, action=ChatAction.TYPING
        )


@pytest.mark.asyncio
async def test_typing_indicator_creates_background_task():
    """typing_indicator yields a background asyncio task."""
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()

    async with typing_indicator(123, bot) as task:
        assert isinstance(task, asyncio.Task)
        assert not task.done()


@pytest.mark.asyncio
async def test_typing_indicator_cancels_task_on_exit():
    """typing_indicator cancels the background loop task on exit."""
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()

    async with typing_indicator(123, bot) as task:
        pass  # Just exit immediately

    # Give event loop a tick to process the cancellation
    await asyncio.sleep(0)
    assert task.cancelled()


@pytest.mark.asyncio
async def test_typing_indicator_loop_sends_periodic_updates():
    """The background loop sends typing action every ~4 seconds."""
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()
    call_count = 0

    async with typing_indicator(123, bot) as task:
        # Wait long enough for at least one periodic send
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Simulate the loop running a few iterations
            mock_sleep.return_value = None
            # Let the event loop tick once to let the task run
            await asyncio.sleep(0)

    # The initial send_chat_action should have been called
    bot.send_chat_action.assert_awaited_with(chat_id=123, action=ChatAction.TYPING)


@pytest.mark.asyncio
async def test_typing_indicator_returns_zero_on_exit():
    """typing_indicator yields a task; task is cancelled in finally block."""
    bot = MagicMock()
    bot.send_chat_action = AsyncMock()

    task_ref = None
    async with typing_indicator(42, bot) as t:
        task_ref = t
        assert not t.done()

    # Give event loop a tick to process the cancellation
    await asyncio.sleep(0)
    # After context manager exits, task should be cancelled
    assert task_ref.cancelled()


# ---------------------------------------------------------------------------
# send_images tests - single image
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_images_single_image_calls_reply_photo():
    """send_images with one image calls reply_photo."""
    message = MagicMock()
    message.reply_photo = AsyncMock()

    fake_img = b"\x89PNG fake image data"

    with patch("builtins.open", MagicMock(return_value=io.BytesIO(fake_img))), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1024):
        total = await send_images(message, ["/tmp/photo.jpg"], {"message_id": 1})

    message.reply_photo.assert_awaited_once()
    message.reply_media_group.assert_not_called()
    assert total == 1024


@pytest.mark.asyncio
async def test_send_images_single_image_returns_file_size():
    """send_images returns the file size for a single image."""
    message = MagicMock()
    message.reply_photo = AsyncMock()

    with patch("builtins.open", MagicMock(return_value=io.BytesIO(b"data"))), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=512):
        total = await send_images(message, ["/tmp/one.png"], {"message_id": 1})

    assert total == 512


@pytest.mark.asyncio
async def test_send_images_single_image_missing_file_returns_zero():
    """send_images returns 0 when file does not exist."""
    message = MagicMock()
    message.reply_photo = AsyncMock()

    with patch("builtins.open", MagicMock(return_value=io.BytesIO(b"data"))), \
         patch("os.path.isfile", return_value=False):
        total = await send_images(message, ["/tmp/gone.jpg"], {"message_id": 1})

    assert total == 0


# ---------------------------------------------------------------------------
# send_images tests - multiple images
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_images_multiple_images_calls_reply_media_group():
    """send_images with multiple images calls reply_media_group."""
    message = MagicMock()
    message.reply_media_group = AsyncMock()

    fake_data = io.BytesIO(b"\x89PNG fake image")

    def fake_open(path, mode="r"):
        return io.BytesIO(b"\x89PNG fake image")

    with patch("builtins.open", side_effect=fake_open), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=1000):
        total = await send_images(
            message,
            ["/tmp/a.jpg", "/tmp/b.jpg", "/tmp/c.jpg"],
            {"message_id": 1},
        )

    message.reply_media_group.assert_awaited_once()
    assert total == 3000


@pytest.mark.asyncio
async def test_send_images_batches_of_10():
    """send_images batches images into groups of 10 for reply_media_group."""
    message = MagicMock()
    message.reply_media_group = AsyncMock()

    paths = [f"/tmp/img_{i}.jpg" for i in range(25)]

    def fake_open(path, mode="r"):
        return io.BytesIO(b"\x89PNG fake image")

    with patch("builtins.open", side_effect=fake_open), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=100):
        total = await send_images(message, paths, {"message_id": 1})

    # 25 images / 10 per batch = 3 batches (10 + 10 + 5)
    assert message.reply_media_group.await_count == 3
    assert total == 2500


@pytest.mark.asyncio
async def test_send_images_file_handles_are_closed():
    """send_images properly closes all file handles after sending."""
    message = MagicMock()
    message.reply_media_group = AsyncMock()

    handles = []

    def fake_open(path, mode="r"):
        h = io.BytesIO(b"\x89PNG fake image")
        h.close = MagicMock(wraps=h.close)
        handles.append(h)
        return h

    with patch("builtins.open", side_effect=fake_open), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=100):
        await send_images(
            message,
            ["/tmp/a.jpg", "/tmp/b.jpg", "/tmp/c.jpg"],
            {"message_id": 1},
        )

    # All file handles should have been closed
    for h in handles:
        h.close.assert_called()


@pytest.mark.asyncio
async def test_send_images_file_handles_closed_on_error():
    """send_images closes file handles even when reply_media_group raises."""
    message = MagicMock()
    message.reply_media_group = AsyncMock(side_effect=Exception("Telegram API error"))

    handles = []

    def fake_open(path, mode="r"):
        h = io.BytesIO(b"\x89PNG fake image")
        h.close = MagicMock(wraps=h.close)
        handles.append(h)
        return h

    with patch("builtins.open", side_effect=fake_open), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=100):
        with pytest.raises(Exception, match="Telegram API error"):
            await send_images(
                message,
                ["/tmp/a.jpg", "/tmp/b.jpg"],
                {"message_id": 1},
            )

    # File handles should still be closed despite the exception
    for h in handles:
        h.close.assert_called()


@pytest.mark.asyncio
async def test_send_images_empty_list():
    """send_images with an empty list returns 0 and makes no API calls."""
    message = MagicMock()
    message.reply_photo = AsyncMock()
    message.reply_media_group = AsyncMock()

    total = await send_images(message, [], {"message_id": 1})

    message.reply_photo.assert_not_awaited()
    message.reply_media_group.assert_not_awaited()
    assert total == 0


@pytest.mark.asyncio
async def test_send_images_total_size_accumulates_across_batches():
    """send_images accumulates file sizes across multiple batches."""
    message = MagicMock()
    message.reply_media_group = AsyncMock()

    def fake_open(path, mode="r"):
        return io.BytesIO(b"\x89PNG fake image")

    with patch("builtins.open", side_effect=fake_open), \
         patch("os.path.isfile", return_value=True), \
         patch("os.path.getsize", return_value=2048):
        total = await send_images(
            message,
            [f"/tmp/img_{i}.jpg" for i in range(15)],
            {"message_id": 1},
        )

    # 15 images * 2048 bytes each
    assert total == 30720
    # 2 batches (10 + 5)
    assert message.reply_media_group.await_count == 2
