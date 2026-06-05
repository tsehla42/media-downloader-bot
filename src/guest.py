"""Bot API 10.0 Guest Mode — unified polling loop.

Telegram Bot API 10.0 (May 2026) introduced Guest Mode, allowing bots to be
invoked via @botname in any chat (even chats the bot isn't a member of). The
bot receives ``guest_message`` updates instead of regular ``message`` updates
when invoked as a guest, and replies via ``answerGuestQuery()``.

This module implements a custom polling loop that takes over from
``app.run_polling()``. Telegram only allows one ``getUpdates`` session per
bot token, so this poller must be the sole consumer. Regular updates are
forwarded to python-telegram-bot's ``Application.process_update()``; guest
updates are handled here.

This module can be replaced when python-telegram-bot adds native Guest Mode
support (tracked upstream).
"""

import asyncio
import json
import logging
import uuid

import httpx
from telegram import Update

from auth import _is_allowed
from config import GUEST_MODE_ENABLED
from logging_config import details_logger

logger = logging.getLogger("media_downloader.guest")

# Telegram long-polling timeout in seconds (max allowed by API)
_LONG_POLL_TIMEOUT = 30

# Base URL for Telegram Bot API
_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class GuestModePoller:
    """Unified polling loop that handles both regular and guest updates.

    Telegram only permits one ``getUpdates`` session per bot token, so this
    poller replaces ``app.run_polling()``. Regular updates are dispatched to
    the python-telegram-bot ``Application``; guest updates are routed to
    ``_handle_guest_message()``.

    Args:
        bot_token: Telegram bot token string.
        application: python-telegram-bot ``Application`` instance (must be
            initialized but not yet running its own polling loop).
    """

    def __init__(self, bot_token: str, application) -> None:
        self.bot_token = bot_token
        self.app = application
        self._offset: int = 0
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """Launch the polling loop as an asyncio task.

        Checks ``GUEST_MODE_ENABLED`` before starting. If disabled, does
        nothing (the caller should fall back to ``app.run_polling()``).
        """
        if not GUEST_MODE_ENABLED:
            logger.info("Guest mode disabled via GUEST_MODE_ENABLED config")
            return

        if self._running:
            logger.warning("GuestModePoller already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("GuestModePoller started")

    def stop(self) -> None:
        """Stop the polling loop."""
        if not self._running:
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("GuestModePoller stopped")

    async def _poll_loop(self) -> None:
        """Long-poll Telegram for updates and route them.

        Regular updates (message, callback_query, my_chat_member) are
        forwarded to ``Application.process_update()``. Guest updates
        (guest_message) go to ``_handle_guest_message()``.

        On error, logs the exception and sleeps 5 seconds before retrying.
        """
        url = _API_BASE.format(token=self.bot_token, method="getUpdates")

        while self._running:
            try:
                params = {
                    "offset": self._offset,
                    "limit": 100,
                    "timeout": _LONG_POLL_TIMEOUT,
                    "allowed_updates": json.dumps(
                        ["message", "callback_query", "my_chat_member", "guest_message"]
                    ),
                }

                async with httpx.AsyncClient(timeout=_LONG_POLL_TIMEOUT + 10) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                if not data.get("ok"):
                    logger.error("getUpdates returned non-ok: %s", data)
                    await asyncio.sleep(5)
                    continue

                for update_raw in data.get("result", []):
                    self._offset = update_raw["update_id"] + 1

                    # Route guest updates to our handler
                    if "guest_message" in update_raw:
                        await self._handle_guest_message(update_raw)
                        continue

                    # Route all other updates to python-telegram-bot
                    update = Update.de_json(update_raw, self.app.bot)
                    if update:
                        await self.app.process_update(update)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in guest polling loop")
                await asyncio.sleep(5)

    async def _handle_guest_message(self, raw_update: dict) -> None:
        """Handle a guest_message update from Bot API 10.0.

        Args:
            raw_update: The raw update dict from getUpdates containing
                a ``guest_message`` key.
        """
        guest_msg = raw_update["guest_message"]
        caller_user = guest_msg.get("guest_bot_caller_user", {})
        guest_query_id = guest_msg.get("guest_query_id", "")
        caller_id = caller_user.get("id", 0)
        text = guest_msg.get("text", "")

        request_id = uuid.uuid4().hex[:8]

        details_logger.info(
            "guest_message received",
            extra={
                "extra_data": {
                    "event": "guest_message",
                    "request_id": request_id,
                    "guest_query_id": guest_query_id,
                    "caller_id": caller_id,
                    "caller_name": caller_user.get("first_name"),
                    "caller_username": caller_user.get("username"),
                    "text": text,
                }
            },
        )

        if not _is_allowed(caller_id):
            details_logger.info(
                "guest_message unauthorized",
                extra={
                    "extra_data": {
                        "event": "guest_message_unauthorized",
                        "request_id": request_id,
                        "caller_id": caller_id,
                    }
                },
            )
            return

        # TODO: Extract URLs from guest message text (Task 5)
        # TODO: Download media from extracted URLs
        # TODO: Reply via answerGuestQuery() with downloaded media
        # TODO: Send answer_guest_query API call with guest_query_id
        details_logger.info(
            "guest_message — URL extraction not yet implemented",
            extra={
                "extra_data": {
                    "event": "guest_message_unimplemented",
                    "request_id": request_id,
                    "guest_query_id": guest_query_id,
                    "caller_id": caller_id,
                    "text": text,
                }
            },
        )
