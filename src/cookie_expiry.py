"""Cookie expiry parsing (Netscape format) and daily admin expiry notices.

Parses the per-cookie expiry timestamp (column 5) of Netscape cookie files
for the meaningful auth cookies per platform, exposes the active file's
expiry, and provides a daily check that DMs bot admins the day before an
auth cookie expires.
"""

import asyncio
import datetime
import logging
from dataclasses import dataclass

from config import BOT_ADMIN_IDS, IG_COOKIES_PATH, TIKTOK_COOKIES_PATH, YT_COOKIES_PATH
from logging_config import service_logger
from messages import MSG_COOKIE_EXPIRY_ALERT

_log = logging.getLogger("cookie_expiry")

# Cookies whose expiry actually kills authentication. Irrelevant short-lived
# cookies (e.g. Instagram `wd`, `dpr`) are deliberately excluded so notices
# only fire for the session credentials that matter.
CRITICAL_COOKIES: dict[str, frozenset[str]] = {
    "ig": frozenset({"sessionid", "sessionid_business"}),
    "yt": frozenset({
        "SID", "HSID", "SSID", "SAPISID", "LSID",
        "__Secure-1PSID", "__Secure-3PSID", "__Secure-1PSIDTS", "__Secure-3PSIDTS",
    }),
    "tt": frozenset({"sessionid", "sid_guard", "sid_tt", "uid_tt", "uid_tt_ss"}),
}

# (platform, expiry) pairs already alerted for — in-memory, resets on restart.
_notified: set[tuple[str, datetime.date]] = set()


@dataclass(frozen=True)
class CookieExpiry:
    """Auth-cookie status parsed from a Netscape cookie file."""

    has_auth: bool
    expiry: datetime.date | None = None
    cookie: str | None = None


def _active_path(platform: str) -> str:
    return {
        "ig": IG_COOKIES_PATH,
        "tt": TIKTOK_COOKIES_PATH,
        "yt": YT_COOKIES_PATH,
    }[platform]


def parse_cookie_expiry(text: str, platform: str) -> CookieExpiry:
    """Parse a Netscape cookie file for the earliest critical-cookie expiry.

    Session cookies (expires=0) count as auth present but carry no date.
    Non-critical cookies never influence the returned expiry.
    """
    critical = CRITICAL_COOKIES.get(platform, frozenset())
    has_auth = False
    earliest: datetime.date | None = None
    earliest_name: str | None = None

    for line in text.splitlines():
        if line.startswith("#HttpOnly_"):
            fields = line[len("#HttpOnly_"):].split("\t")
        elif line.startswith("#") or not line.strip():
            continue
        else:
            fields = line.split("\t")
        if len(fields) < 6:
            continue
        name = fields[5]
        if name not in critical:
            continue
        has_auth = True
        expires = fields[4]
        if not expires.isdigit():
            continue
        exp = int(expires)
        if exp <= 0:
            continue
        day = datetime.datetime.fromtimestamp(exp).date()
        if earliest is None or day < earliest:
            earliest, earliest_name = day, name

    return CookieExpiry(has_auth=has_auth, expiry=earliest, cookie=earliest_name)


def active_cookie_expiry(platform: str) -> CookieExpiry:
    """Read the active cookie file for a platform and parse its expiry."""
    try:
        with open(_active_path(platform), encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return CookieExpiry(has_auth=False)
    if not text.strip():
        return CookieExpiry(has_auth=False)
    return parse_cookie_expiry(text, platform)


def _when_phrase(days_left: int, expiry: datetime.date) -> str:
    if days_left < 0:
        return f"expired ({expiry.isoformat()})"
    if days_left == 0:
        return f"expire today ({expiry.isoformat()})"
    return f"expire tomorrow ({expiry.isoformat()})"


async def check_and_notify(bot) -> None:
    """DM every bot admin when any platform's auth cookie is <=1 day from expiry.

    Each (platform, expiry) pair alerts at most once per process lifetime.
    """
    today = datetime.date.today()
    for platform in ("tt", "ig", "yt"):
        result = active_cookie_expiry(platform)
        if result.expiry is None:
            continue
        days_left = (result.expiry - today).days
        if days_left > 1:
            continue
        key = (platform, result.expiry)
        if key in _notified:
            continue
        text = MSG_COOKIE_EXPIRY_ALERT.format(
            platform=platform, when=_when_phrase(days_left, result.expiry)
        )
        for admin_id in sorted(BOT_ADMIN_IDS):
            try:
                await bot.send_message(admin_id, text=text)
            except Exception as e:
                _log.warning("cookie expiry alert to admin %s failed: %s", admin_id, e)
        _notified.add(key)
        service_logger.info(
            "cookie_expiry_alert",
            extra={"extra_data": {
                "event": "cookie_expiry_alert",
                "platform": platform,
                "expiry": result.expiry.isoformat(),
                "days_left": days_left,
            }},
        )


async def expiry_check_loop(bot, interval_seconds: int = 24 * 3600) -> None:
    """Run check_and_notify daily for the lifetime of the process."""
    while True:
        try:
            await check_and_notify(bot)
        except Exception as e:
            _log.warning("cookie expiry check failed: %s", e)
        await asyncio.sleep(interval_seconds)
