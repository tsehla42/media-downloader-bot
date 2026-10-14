"""Tests for cookie_expiry.py — Netscape expiry parsing and daily admin notices."""

import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cookie_expiry import (
    CookieExpiry,
    active_cookie_expiry,
    check_and_notify,
    parse_cookie_expiry,
)

ADMIN_A = 1000
ADMIN_B = 3000


def _row(name, expires, domain=".instagram.com", flag="TRUE"):
    return f"{domain}\t{flag}\t/\tTRUE\t{expires}\t{name}\tvalue\n"


def _days_from_now(days: int) -> int:
    return int(
        (datetime.datetime.combine(
            datetime.date.today() + datetime.timedelta(days=days),
            datetime.time(12, 0),
        )).timestamp()
    )


class TestParseCookieExpiry:
    def test_returns_critical_cookie_expiry_not_earlier_noise(self):
        # wd expires tomorrow but is irrelevant; sessionid is the auth cookie
        text = (
            "# Netscape HTTP Cookie File\n"
            + _row("wd", _days_from_now(7))
            + _row("sessionid", _days_from_now(300))
        )
        result = parse_cookie_expiry(text, "ig")
        assert result.has_auth is True
        assert result.cookie == "sessionid"
        assert result.expiry == datetime.date.today() + datetime.timedelta(days=300)

    def test_missing_auth_cookie(self):
        text = "# Netscape HTTP Cookie File\n" + _row("wd", _days_from_now(7))
        result = parse_cookie_expiry(text, "ig")
        assert result.has_auth is False
        assert result.expiry is None
        assert result.cookie is None

    def test_session_auth_cookie_has_no_expiry(self):
        text = _row("sessionid", 0)
        result = parse_cookie_expiry(text, "ig")
        assert result.has_auth is True
        assert result.expiry is None

    def test_httponly_prefixed_line_parsed(self):
        text = (
            "#HttpOnly_.instagram.com\tTRUE\t/\tTRUE\t"
            + str(_days_from_now(300))
            + "\tsessionid\tvalue\n"
        )
        result = parse_cookie_expiry(text, "ig")
        assert result.has_auth is True
        assert result.expiry == datetime.date.today() + datetime.timedelta(days=300)

    def test_earliest_of_multiple_critical_cookies_wins(self):
        text = (
            _row("SAPISID", _days_from_now(200), domain=".youtube.com")
            + _row("SID", _days_from_now(50), domain=".youtube.com")
        )
        result = parse_cookie_expiry(text, "yt")
        assert result.cookie == "SID"
        assert result.expiry == datetime.date.today() + datetime.timedelta(days=50)

    def test_tiktok_sessionid_recognized(self):
        text = _row("sessionid", _days_from_now(20), domain=".tiktok.com")
        result = parse_cookie_expiry(text, "tt")
        assert result.has_auth is True
        assert result.cookie == "sessionid"

    def test_empty_text(self):
        result = parse_cookie_expiry("", "ig")
        assert result == CookieExpiry(has_auth=False)


class TestActiveCookieExpiry:
    def test_reads_active_ig_path(self, tmp_path):
        cookie_file = tmp_path / "ig-cookies.txt"
        cookie_file.write_text(_row("sessionid", _days_from_now(100)))
        with patch("cookie_expiry.IG_COOKIES_PATH", str(cookie_file)):
            result = active_cookie_expiry("ig")
        assert result.has_auth is True
        assert result.expiry == datetime.date.today() + datetime.timedelta(days=100)

    def test_missing_file(self):
        with patch("cookie_expiry.IG_COOKIES_PATH", "/nonexistent/ig-cookies.txt"):
            result = active_cookie_expiry("ig")
        assert result == CookieExpiry(has_auth=False)


class TestLoopStartup:
    @pytest.mark.asyncio
    async def test_post_init_schedules_daily_expiry_check(self):
        from bot import post_init

        app = MagicMock()
        app.bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
        app.bot.set_my_commands = AsyncMock()
        app.create_task = MagicMock()

        await post_init(app)

        app.create_task.assert_called_once()
        coro = app.create_task.call_args[0][0]
        coro.close()  # never awaited in test — close to avoid warnings


class TestCheckAndNotify:
    @pytest.fixture(autouse=True)
    def fresh_notified(self):
        import cookie_expiry
        cookie_expiry._notified.clear()
        yield
        cookie_expiry._notified.clear()

    def _active_path_patch(self, tmp_path, text):
        cookie_file = tmp_path / "ig-cookies.txt"
        cookie_file.write_text(text)
        return patch("cookie_expiry.IG_COOKIES_PATH", str(cookie_file))

    @pytest.mark.asyncio
    async def test_notifies_admins_one_day_before_expiry(self, tmp_path):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with self._active_path_patch(tmp_path, _row("sessionid", _days_from_now(1))), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A, ADMIN_B}):
            await check_and_notify(bot)

        assert bot.send_message.call_count == 2
        texts = {c[0][0]: c[1]["text"] for c in bot.send_message.call_args_list}
        assert set(texts) == {ADMIN_A, ADMIN_B}
        for text in texts.values():
            assert "expire tomorrow" in text
            assert "cookie update ig" in text

    @pytest.mark.asyncio
    async def test_no_notification_when_far_from_expiry(self, tmp_path):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with self._active_path_patch(tmp_path, _row("sessionid", _days_from_now(90))), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A}):
            await check_and_notify(bot)
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_notifies_once_per_expiry(self, tmp_path):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with self._active_path_patch(tmp_path, _row("sessionid", _days_from_now(1))), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A}):
            await check_and_notify(bot)
            await check_and_notify(bot)
        assert bot.send_message.call_count == 1

    @pytest.mark.asyncio
    async def test_expired_cookies_alerted(self, tmp_path):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with self._active_path_patch(tmp_path, _row("sessionid", _days_from_now(-3))), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A}):
            await check_and_notify(bot)
        bot.send_message.assert_called_once()
        assert "expired" in bot.send_message.call_args[1]["text"]

    @pytest.mark.asyncio
    async def test_expires_today_alerted(self, tmp_path):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with self._active_path_patch(tmp_path, _row("sessionid", _days_from_now(0))), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A}):
            await check_and_notify(bot)
        bot.send_message.assert_called_once()
        assert "expire today" in bot.send_message.call_args[1]["text"]

    @pytest.mark.asyncio
    async def test_no_auth_cookie_no_notification(self, tmp_path):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with self._active_path_patch(tmp_path, _row("wd", _days_from_now(1))), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A}):
            await check_and_notify(bot)
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_missing_cookie_file_no_notification(self):
        bot = MagicMock()
        bot.send_message = AsyncMock()
        with patch("cookie_expiry.IG_COOKIES_PATH", "/nonexistent/ig-cookies.txt"), \
             patch("cookie_expiry.BOT_ADMIN_IDS", {ADMIN_A}):
            await check_and_notify(bot)
        bot.send_message.assert_not_called()
