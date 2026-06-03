# src/telegram_utils.py
"""Telegram helper utilities: typing indicators, image sending."""

import asyncio
import os
from contextlib import asynccontextmanager
from telegram import InputMediaPhoto
from telegram.constants import ChatAction


@asynccontextmanager
async def typing_indicator(chat_id: int, bot):
    """Async context manager that shows typing indicator while active.

    Usage:
        async with typing_indicator(chat_id, bot):
            # do work
            pass
    """
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    async def _loop():
        try:
            while True:
                await asyncio.sleep(4)
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass  # Silently ignore typing errors (e.g. bot kicked from chat)

    task = asyncio.create_task(_loop())
    try:
        yield task
    finally:
        task.cancel()


async def send_images(message, images: list[str], reply_params: dict) -> int:
    """Send images to Telegram, handling single photo vs media group batching.

    Args:
        message: Telegram message object to reply to
        images: List of file paths to send
        reply_params: reply_parameters dict for the reply

    Returns:
        Total size of images in bytes
    """
    total_size = 0

    if len(images) == 1:
        with open(images[0], "rb") as f:
            await message.reply_photo(
                photo=f,
                reply_parameters=reply_params,
            )
        if os.path.isfile(images[0]):
            total_size = os.path.getsize(images[0])
    else:
        for i in range(0, len(images), 10):
            batch = images[i:i+10]
            handles = [open(img, "rb") for img in batch]
            try:
                media = [InputMediaPhoto(h) for h in handles]
                await message.reply_media_group(
                    media=media,
                    reply_parameters=reply_params,
                )
            finally:
                for h in handles:
                    h.close()
        for img in images:
            if os.path.isfile(img):
                total_size += os.path.getsize(img)

    return total_size
