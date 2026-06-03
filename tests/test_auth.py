"""Unit tests for auth.py authorization checks."""

import pytest
from unittest.mock import MagicMock, patch


def _make_update(chat_type="private", chat_id=123456, user_id=123456, from_user=True):
    """Helper to create a mock Update with the given properties."""
    update = MagicMock()
    update.effective_chat.type = chat_type
    update.effective_chat.id = chat_id

    if from_user:
        update.message = MagicMock()
        update.message.from_user = MagicMock()
        update.message.from_user.id = user_id
    else:
        update.message = MagicMock()
        update.message.from_user = None

    return update


class TestIsGroupChat:
    def test_group_chat_returns_true(self):
        from auth import is_group_chat

        update = _make_update(chat_type="group")
        assert is_group_chat(update) is True

    def test_supergroup_chat_returns_true(self):
        from auth import is_group_chat

        update = _make_update(chat_type="supergroup")
        assert is_group_chat(update) is True

    def test_private_chat_returns_false(self):
        from auth import is_group_chat

        update = _make_update(chat_type="private")
        assert is_group_chat(update) is False

    def test_channel_chat_returns_false(self):
        from auth import is_group_chat

        update = _make_update(chat_type="channel")
        assert is_group_chat(update) is False


class TestIsAllowed:
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_empty_allowlist_allows_all(self):
        from auth import _is_allowed

        assert _is_allowed(999999) is True

    @patch("auth.ALLOWED_USER_IDS", {111, 222})
    def test_user_in_allowlist_allowed(self):
        from auth import _is_allowed

        assert _is_allowed(111) is True
        assert _is_allowed(222) is True

    @patch("auth.ALLOWED_USER_IDS", {111, 222})
    def test_user_not_in_allowlist_denied(self):
        from auth import _is_allowed

        assert _is_allowed(333) is False


class TestIsAllowedGroup:
    @patch("auth.ALLOWED_GROUP_IDS", set())
    def test_empty_allowlist_allows_all(self):
        from auth import _is_allowed_group

        assert _is_allowed_group(999999) is True

    @patch("auth.ALLOWED_GROUP_IDS", {100, 200})
    def test_group_in_allowlist_allowed(self):
        from auth import _is_allowed_group

        assert _is_allowed_group(100) is True
        assert _is_allowed_group(200) is True

    @patch("auth.ALLOWED_GROUP_IDS", {100, 200})
    def test_group_not_in_allowlist_denied(self):
        from auth import _is_allowed_group

        assert _is_allowed_group(300) is False


class TestIsAuthorized:
    @patch("auth.ALLOWED_GROUP_IDS", set())
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_group_chat_empty_group_allowlist_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="group", chat_id=100)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_GROUP_IDS", {100})
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_group_chat_in_group_allowlist_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="group", chat_id=100)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_GROUP_IDS", {100})
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_group_chat_not_in_group_allowlist_denied(self):
        from auth import is_authorized

        update = _make_update(chat_type="group", chat_id=999)
        assert is_authorized(update) is False

    @patch("auth.ALLOWED_GROUP_IDS", set())
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_supergroup_chat_empty_group_allowlist_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="supergroup", chat_id=200)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_USER_IDS", set())
    def test_private_chat_empty_user_allowlist_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="private", user_id=555)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_USER_IDS", {111, 222})
    def test_private_chat_user_in_allowlist_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="private", user_id=111)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_USER_IDS", {111, 222})
    def test_private_chat_user_not_in_allowlist_denied(self):
        from auth import is_authorized

        update = _make_update(chat_type="private", user_id=333)
        assert is_authorized(update) is False

    @patch("auth.ALLOWED_USER_IDS", {111})
    def test_private_chat_from_user_none_denied(self):
        from auth import is_authorized

        update = _make_update(chat_type="private", from_user=False)
        assert is_authorized(update) is False
