"""Tests for src/cookies.py — Instagram cookie refresh."""

import os
import time
from http.cookiejar import Cookie, CookieJar
from unittest.mock import patch, MagicMock

import pytest


class TestCheckCookiesStaleness:
    """Tests for check_cookies_staleness()."""

    def test_returns_true_when_file_missing(self, tmp_path):
        """Missing cookies file is considered stale."""
        from cookies import check_cookies_staleness
        result = check_cookies_staleness(str(tmp_path / "nonexistent.txt"))
        assert result is True

    def test_returns_false_when_recent(self, tmp_path):
        """Recently written cookies file is not stale."""
        from cookies import check_cookies_staleness
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")
        result = check_cookies_staleness(str(cookies_file), max_age_days=3)
        assert result is False

    def test_returns_true_when_old(self, tmp_path):
        """Cookies file older than max_age_days is stale."""
        from cookies import check_cookies_staleness
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")
        old_time = time.time() - (4 * 86400)
        os.utime(str(cookies_file), (old_time, old_time))
        result = check_cookies_staleness(str(cookies_file), max_age_days=3)
        assert result is True

    def test_custom_max_age(self, tmp_path):
        """Custom max_age_days parameter is respected."""
        from cookies import check_cookies_staleness
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")
        old_time = time.time() - (2 * 86400)
        os.utime(str(cookies_file), (old_time, old_time))
        assert check_cookies_staleness(str(cookies_file), max_age_days=1) is True
        assert check_cookies_staleness(str(cookies_file), max_age_days=7) is False


class TestExportCookiesToNetscape:
    """Tests for _export_cookies_to_netscape()."""

    def _make_cookie(self, name, value, domain=".instagram.com", path="/",
                     secure=True, expires=1750000000):
        """Create a Cookie object for testing."""
        return Cookie(
            version=0, name=name, value=value,
            port=None, port_specified=False,
            domain=domain, domain_specified=True, domain_initial_dot=domain.startswith("."),
            path=path, path_specified=True,
            secure=secure, expires=expires,
            discard=False, comment=None, comment_url=None,
            rest={}, rfc2109=False,
        )

    def test_exports_instagram_cookies(self, tmp_path):
        """Only Instagram domain cookies are exported."""
        from cookies import _export_cookies_to_netscape
        jar = CookieJar()
        jar.set_cookie(self._make_cookie("sessionid", "abc123", domain=".instagram.com"))
        jar.set_cookie(self._make_cookie("other", "xyz", domain=".other.com"))

        output = tmp_path / "cookies.txt"
        _export_cookies_to_netscape(jar, str(output))

        content = output.read_text()
        assert "sessionid" in content
        assert "abc123" in content
        assert ".instagram.com" in content
        assert "other" not in content

    def test_netscape_format_correct(self, tmp_path):
        """Output follows Netscape cookies.txt format."""
        from cookies import _export_cookies_to_netscape
        jar = CookieJar()
        jar.set_cookie(self._make_cookie("csrftoken", "tok123"))

        output = tmp_path / "cookies.txt"
        _export_cookies_to_netscape(jar, str(output))

        lines = [l for l in output.read_text().splitlines() if not l.startswith("#")]
        assert len(lines) == 1
        parts = lines[0].split("\t")
        assert len(parts) == 7
        assert parts[0] == ".instagram.com"
        assert parts[1] == "TRUE"
        assert parts[2] == "/"
        assert parts[3] == "TRUE"
        assert parts[4] == "1750000000"
        assert parts[5] == "csrftoken"
        assert parts[6] == "tok123"

    def test_empty_jar_creates_file_with_header(self, tmp_path):
        """Even with no cookies, file gets the Netscape header."""
        from cookies import _export_cookies_to_netscape
        jar = CookieJar()
        output = tmp_path / "cookies.txt"
        _export_cookies_to_netscape(jar, str(output))

        content = output.read_text()
        assert content.startswith("# Netscape HTTP Cookie File")

    def test_writes_to_file_atomically(self, tmp_path):
        """Output file is created even if no Instagram cookies exist."""
        from cookies import _export_cookies_to_netscape
        jar = CookieJar()
        jar.set_cookie(self._make_cookie("test", "val", domain=".notinstagram.com"))
        output = tmp_path / "cookies.txt"
        _export_cookies_to_netscape(jar, str(output))
        assert output.exists()


class TestLoginWithSession:
    """Tests for _login_with_session()."""

    def test_loads_existing_session(self, tmp_path):
        """Reuses session from session_path when valid."""
        from cookies import _login_with_session
        mock_cl = MagicMock()
        session_file = tmp_path / "session.json"
        session_file.write_text('{"session": "data"}')

        result = _login_with_session(mock_cl, "user", "pass", str(session_file))

        mock_cl.load_settings.assert_called_once_with(str(session_file))
        mock_cl.login.assert_called_once_with("user", "pass")
        assert result is True

    def test_falls_back_to_fresh_login(self, tmp_path):
        """Falls back to fresh login when session loading fails."""
        from cookies import _login_with_session
        mock_cl = MagicMock()
        mock_cl.load_settings.side_effect = Exception("bad session")
        session_file = tmp_path / "session.json"
        session_file.write_text('{"session": "data"}')

        result = _login_with_session(mock_cl, "user", "pass", str(session_file))

        mock_cl.load_settings.assert_called_once()
        mock_cl.login.assert_called_once_with("user", "pass")
        assert result is True

    def test_returns_false_on_login_failure(self, tmp_path):
        """Returns False when all login attempts fail."""
        from cookies import _login_with_session
        mock_cl = MagicMock()
        mock_cl.load_settings.side_effect = Exception("bad session")
        mock_cl.login.side_effect = Exception("login failed")
        session_file = tmp_path / "session.json"
        session_file.write_text('{}')

        result = _login_with_session(mock_cl, "user", "pass", str(session_file))

        assert result is False

    def test_no_session_file_fresh_login(self, tmp_path):
        """No session file → fresh login only."""
        from cookies import _login_with_session
        mock_cl = MagicMock()
        session_file = tmp_path / "nonexistent.json"

        result = _login_with_session(mock_cl, "user", "pass", str(session_file))

        mock_cl.load_settings.assert_not_called()
        mock_cl.login.assert_called_once_with("user", "pass")
        assert result is True


class TestRefreshInstagramCookies:
    """Tests for refresh_instagram_cookies()."""

    def test_skips_refresh_when_fresh(self, tmp_path):
        """Does not login when cookies are still fresh."""
        from cookies import refresh_instagram_cookies
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("# Netscape HTTP Cookie File\n")

        result = refresh_instagram_cookies(
            "user", "pass",
            str(tmp_path / "session.json"),
            str(cookies_file),
            max_age_days=3,
        )

        assert result is True

    def test_refreshes_when_stale(self, tmp_path):
        """Logs in and exports cookies when stale."""
        from cookies import refresh_instagram_cookies
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("old cookies")
        old_time = time.time() - (4 * 86400)
        os.utime(str(cookies_file), (old_time, old_time))

        mock_cl = MagicMock()
        mock_cl.get_settings.return_value = {
            "authorization_data": {"sessionid": "abc123", "ds_user_id": "12345"}
        }

        with patch("cookies.Client", return_value=mock_cl):
            result = refresh_instagram_cookies(
                "user", "pass",
                str(tmp_path / "session.json"),
                str(cookies_file),
                max_age_days=3,
            )

        assert result is True
        mock_cl.login.assert_called()
        mock_cl.dump_settings.assert_called_once()
        # Verify cookies file was written with sessionid
        content = cookies_file.read_text()
        assert "sessionid" in content
        assert "abc123" in content

    def test_returns_false_on_login_failure(self, tmp_path):
        """Returns False and keeps old cookies when login fails."""
        from cookies import refresh_instagram_cookies
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("old cookies")
        old_time = time.time() - (4 * 86400)
        os.utime(str(cookies_file), (old_time, old_time))

        mock_cl = MagicMock()
        mock_cl.login.side_effect = Exception("login failed")

        with patch("cookies.Client", return_value=mock_cl):
            result = refresh_instagram_cookies(
                "user", "pass",
                str(tmp_path / "session.json"),
                str(cookies_file),
                max_age_days=3,
            )

        assert result is False
        assert cookies_file.read_text() == "old cookies"

    def test_force_skips_staleness_check(self, tmp_path):
        """--force refreshes even when cookies are fresh."""
        from cookies import refresh_instagram_cookies
        cookies_file = tmp_path / "ig-cookies.txt"
        cookies_file.write_text("fresh cookies")

        mock_cl = MagicMock()
        mock_cl.get_settings.return_value = {
            "authorization_data": {"sessionid": "abc123", "ds_user_id": "12345"}
        }

        with patch("cookies.Client", return_value=mock_cl):
            result = refresh_instagram_cookies(
                "user", "pass",
                str(tmp_path / "session.json"),
                str(cookies_file),
                max_age_days=3,
                force=True,
            )

        assert result is True
        mock_cl.login.assert_called()
