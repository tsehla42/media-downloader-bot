"""Unit tests for auth.py authorization checks and config loading."""

import json
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open


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


class TestIsPrivateChat:
    def test_private_chat_returns_true(self):
        from auth import is_private_chat

        chat = MagicMock()
        chat.type = "private"
        assert is_private_chat(chat) is True

    def test_group_chat_returns_false(self):
        from auth import is_private_chat

        chat = MagicMock()
        chat.type = "group"
        assert is_private_chat(chat) is False

    def test_supergroup_chat_returns_false(self):
        from auth import is_private_chat

        chat = MagicMock()
        chat.type = "supergroup"
        assert is_private_chat(chat) is False

    def test_missing_type_returns_false(self):
        from auth import is_private_chat

        chat = MagicMock(spec=[])
        assert is_private_chat(chat) is False


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
    @patch("auth.ALLOWED_IDS_CONFIGURED", False)
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_no_ids_configured_allows_all(self):
        from auth import _is_allowed

        assert _is_allowed(999999) is True

    @patch("auth.ALLOWED_IDS_CONFIGURED", True)
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_ids_configured_but_empty_denies_all(self):
        from auth import _is_allowed

        assert _is_allowed(999999) is False

    @patch("auth.ALLOWED_IDS_CONFIGURED", True)
    @patch("auth.ALLOWED_USER_IDS", {111, 222})
    def test_user_in_allowlist_allowed(self):
        from auth import _is_allowed

        assert _is_allowed(111) is True
        assert _is_allowed(222) is True

    @patch("auth.ALLOWED_IDS_CONFIGURED", True)
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


class TestAuthHelpers:
    def test_is_bot_admin_with_admin_id(self):
        """Admin ID in set returns True."""
        from auth import is_bot_admin
        with patch('auth.BOT_ADMIN_IDS', {123456}):
            assert is_bot_admin(123456) is True

    def test_is_bot_admin_with_non_admin_id(self):
        """Non-admin ID returns False."""
        from auth import is_bot_admin
        with patch('auth.BOT_ADMIN_IDS', {123456}):
            assert is_bot_admin(999999) is False

    def test_is_bot_admin_empty_set(self):
        """Empty admin set returns True for all (allow all)."""
        from auth import is_bot_admin
        with patch('auth.BOT_ADMIN_IDS', set()):
            assert is_bot_admin(123456) is True

    def test_was_notified_new_user(self):
        """New user not in notified set returns False."""
        from auth import was_notified, _already_told_users
        _already_told_users.clear()
        assert was_notified(123456) is False

    def test_was_notified_after_marking(self):
        """User in notified set returns True."""
        from auth import was_notified, mark_notified, _already_told_users
        _already_told_users.clear()
        mark_notified(123456)
        assert was_notified(123456) is True

    def test_mark_notified_adds_to_set(self):
        """mark_notified adds user to set."""
        from auth import mark_notified, _already_told_users
        _already_told_users.clear()
        mark_notified(123456)
        assert 123456 in _already_told_users


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
    def test_group_chat_not_in_group_allowlist_still_allowed(self):
        """Groups are always allowed - bot only exists if admin added it."""
        from auth import is_authorized

        update = _make_update(chat_type="group", chat_id=999)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_GROUP_IDS", set())
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_supergroup_chat_empty_group_allowlist_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="supergroup", chat_id=200)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_IDS_CONFIGURED", False)
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_private_chat_no_ids_configured_allowed(self):
        from auth import is_authorized

        update = _make_update(chat_type="private", user_id=555)
        assert is_authorized(update) is True

    @patch("auth.ALLOWED_IDS_CONFIGURED", True)
    @patch("auth.ALLOWED_USER_IDS", set())
    def test_private_chat_ids_configured_but_empty_denied(self):
        from auth import is_authorized

        update = _make_update(chat_type="private", user_id=555)
        assert is_authorized(update) is False

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


class TestConfigLoading:
    def test_load_ids_from_env_only(self):
        """When no JSON file exists, load from env var only."""
        with patch.dict(os.environ, {"ALLOWED_USER_IDS": "111,222,333"}), \
             patch("config.os.path.isfile", return_value=False):
            from config import _load_allowed_user_ids
            ids, configured = _load_allowed_user_ids()
            assert ids == {111, 222, 333}
            assert configured is True

    def test_load_ids_from_json_only(self):
        """When JSON file exists (new format), load from it."""
        json_content = [{"id": 111, "first_name": "Test"}, {"id": 222, "first_name": "Test2"}]
        with patch("config.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(json_content))):
            from config import _load_allowed_user_ids
            ids, configured = _load_allowed_user_ids()
            assert 111 in ids
            assert 222 in ids
            assert isinstance(ids, set)
            assert configured is True

    def test_load_ids_from_json_old_format(self):
        """When JSON file exists (old dict format), load from it."""
        json_content = {"allowed_user_ids": ["111", "222"]}
        with patch("config.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(json_content))):
            from config import _load_allowed_user_ids
            ids, configured = _load_allowed_user_ids()
            assert 111 in ids
            assert 222 in ids
            assert configured is True

    def test_load_ids_merge_json_and_env(self):
        """When both sources exist, merge them."""
        json_content = [{"id": 111, "first_name": "FromJSON"}]
        with patch.dict(os.environ, {"ALLOWED_USER_IDS": "222,333"}), \
             patch("config.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(json_content))):
            from config import _load_allowed_user_ids
            ids, configured = _load_allowed_user_ids()
            assert ids == {111, 222, 333}
            assert configured is True

    def test_load_ids_empty_env_and_no_json(self):
        """When no JSON and empty env, return empty set and configured=False."""
        with patch("config.os.path.isfile", return_value=False), \
             patch.dict(os.environ, {"ALLOWED_USER_IDS": ""}):
            from config import _load_allowed_user_ids
            ids, configured = _load_allowed_user_ids()
            assert ids == set()
            assert configured is False

    def test_load_ids_json_malformed(self):
        """When JSON is malformed, fall back to env var only."""
        with patch("config.os.path.isfile", return_value=True), \
             patch("builtins.open", mock_open(read_data="not valid json")), \
             patch.dict(os.environ, {"ALLOWED_USER_IDS": "444"}):
            from config import _load_allowed_user_ids
            ids, configured = _load_allowed_user_ids()
            assert ids == {444}
            assert configured is True


class TestBotAdminIds:
    def test_load_admin_ids_from_env(self):
        """Load admin IDs from BOT_ADMIN_IDS env var."""
        with patch.dict(os.environ, {"BOT_ADMIN_IDS": "100,200,300"}):
            from config import _load_bot_admin_ids
            result = _load_bot_admin_ids()
            assert result == {100, 200, 300}

    def test_load_admin_ids_empty(self):
        """When BOT_ADMIN_IDS is empty, return empty set."""
        with patch.dict(os.environ, {"BOT_ADMIN_IDS": ""}):
            from config import _load_bot_admin_ids
            result = _load_bot_admin_ids()
            assert result == set()

    def test_load_admin_ids_not_set(self):
        """When BOT_ADMIN_IDS is not set, return empty set."""
        with patch.dict(os.environ, {}, clear=True):
            from config import _load_bot_admin_ids
            result = _load_bot_admin_ids()
            assert result == set()


class TestRejectIfUnauthorized:
    @pytest.mark.asyncio
    async def test_returns_false_for_authorized(self):
        from auth import reject_if_unauthorized

        update = MagicMock()
        update.message.from_user.id = 123
        update.effective_chat.type = "private"
        with patch("auth.is_authorized", return_value=True):
            result = await reject_if_unauthorized(update, "/test")
            assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_for_unauthorized(self):
        from auth import reject_if_unauthorized
        from messages import MSG_UNAUTHORIZED

        update = MagicMock()
        update.message.from_user.id = 123
        update.message.reply_text = AsyncMock()
        update.effective_chat.type = "private"
        with patch("auth.is_authorized", return_value=False), \
             patch("auth.was_notified", return_value=False), \
             patch("auth.mark_notified"), \
             patch("auth.log_unauthorized_access"):
            result = await reject_if_unauthorized(update, "/test")
            assert result is True
            update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_reply_if_already_notified(self):
        from auth import reject_if_unauthorized

        update = MagicMock()
        update.message.from_user.id = 123
        update.effective_chat.type = "private"
        with patch("auth.is_authorized", return_value=False), \
             patch("auth.was_notified", return_value=True), \
             patch("auth.mark_notified"), \
             patch("auth.log_unauthorized_access"):
            result = await reject_if_unauthorized(update, "/test")
            assert result is True
            update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_silent_skips_in_groups(self):
        from auth import reject_if_unauthorized

        update = MagicMock()
        update.message.from_user.id = 123
        update.effective_chat.type = "group"
        with patch("auth.is_authorized", return_value=False), \
             patch("auth.is_group_chat", return_value=True):
            result = await reject_if_unauthorized(update, "/test", group_silent=True)
            assert result is True
            update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_passes_reply_parameters(self):
        from auth import reject_if_unauthorized
        from messages import MSG_UNAUTHORIZED

        update = MagicMock()
        update.message.from_user.id = 123
        update.message.reply_text = AsyncMock()
        update.effective_chat.type = "private"
        params = {"message_id": 456}
        with patch("auth.is_authorized", return_value=False), \
             patch("auth.was_notified", return_value=False), \
             patch("auth.mark_notified"), \
             patch("auth.log_unauthorized_access"):
            result = await reject_if_unauthorized(update, "/test", reply_parameters=params)
            assert result is True
            update.message.reply_text.assert_called_once_with(
                MSG_UNAUTHORIZED, reply_parameters=params
            )
