"""Instagram cookie refresh via instagrapi.

Handles login, session persistence, and Netscape cookies.txt export
for use by gallery-dl and yt-dlp.
"""

import logging
import os
import time
from http.cookiejar import CookieJar

from instagrapi import Client

logger = logging.getLogger(__name__)


def check_cookies_staleness(cookies_path: str, max_age_days: int = 7) -> bool:
    """Check if cookies file is stale (older than max_age_days).

    Returns True if file is missing or older than threshold.
    """
    if not os.path.isfile(cookies_path):
        return True
    mtime = os.path.getmtime(cookies_path)
    age_seconds = time.time() - mtime
    return age_seconds > (max_age_days * 86400)


def _export_cookies_to_netscape(cookie_jar: CookieJar, output_path: str,
                                 domain: str = ".instagram.com") -> None:
    """Convert a RequestsCookieJar to Netscape cookies.txt format.

    Only exports cookies matching the specified domain.
    Writes the standard Netscape HTTP Cookie File format used by
    curl, gallery-dl, and yt-dlp.
    """
    lines = ["# Netscape HTTP Cookie File"]

    for cookie in cookie_jar:
        if not cookie.domain.endswith(domain):
            continue
        secure = "TRUE" if cookie.secure else "FALSE"
        tailmatch = "TRUE" if cookie.domain.startswith(".") else "FALSE"
        expires = str(cookie.expires) if cookie.expires else "0"
        line = "\t".join([
            cookie.domain,
            tailmatch,
            cookie.path or "/",
            secure,
            expires,
            cookie.name,
            cookie.value,
        ])
        lines.append(line)

    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def _login_with_session(cl, username: str, password: str,
                        session_path: str) -> bool:
    """Try to login using saved session, fallback to fresh login.

    Returns True on success, False on failure.
    """
    # Try loading existing session first
    if os.path.isfile(session_path):
        try:
            cl.load_settings(session_path)
            cl.login(username, password)
            logger.info("Logged in using saved session")
            return True
        except Exception as e:
            logger.warning("Session login failed (%s), trying fresh login", e)

    # Fresh login
    try:
        cl.login(username, password)
        logger.info("Logged in with fresh credentials")
        return True
    except Exception as e:
        logger.error("Login failed: %s", e)
        return False


def refresh_instagram_cookies(username: str, password: str,
                               session_path: str, cookies_path: str,
                               max_age_days: int = 7,
                               force: bool = False) -> bool:
    """Refresh Instagram cookies if stale.

    Returns True if cookies are fresh or were successfully refreshed.
    Returns False if refresh failed (existing cookies preserved).
    """
    if not force and not check_cookies_staleness(cookies_path, max_age_days):
        logger.info("Cookies are fresh (age < %d days), skipping refresh", max_age_days)
        return True

    if not username or not password:
        logger.error("IG_USERNAME and IG_PASSWORD must be set")
        return False

    logger.info("Refreshing Instagram cookies...")

    cl = Client()
    success = _login_with_session(cl, username, password, session_path)

    if not success:
        logger.error("Cookie refresh failed — existing cookies preserved")
        return False

    try:
        cl.dump_settings(session_path)
        # Export cookies from authorization_data (instagrapi stores auth there)
        settings = cl.get_settings()
        auth = settings.get("authorization_data", {})
        sessionid = auth.get("sessionid", "")
        ds_user_id = auth.get("ds_user_id", "")
        if sessionid:
            with open(cookies_path, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{sessionid}\n")
                if ds_user_id:
                    f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tds_user_id\t{ds_user_id}\n")
            logger.info("Cookies exported to %s", cookies_path)
        else:
            logger.warning("No sessionid in authorization_data — cookies not exported")
        return True
    except Exception as e:
        logger.error("Failed to export cookies: %s", e)
        return False
