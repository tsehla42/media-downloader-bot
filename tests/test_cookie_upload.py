"""Tests for cookie_upload.py — admin-only cookie file upload via document message."""

import datetime
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from messages import (
    MSG_COOKIE_INVALID_CAPTION,
    MSG_COOKIE_INVALID_FILE,
    MSG_COOKIE_NO_CAPTION_HINT,
    MSG_COOKIE_UPDATED,
)

ADMIN_ID = 1000
OTHER_ID = 2000

NETSCAPE_CONTENT = (
    "# Netscape HTTP Cookie File\n"
    ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tabc123\n"
)


def _make_update(
    *,
    caption=None,
    filename="cookies.txt",
    chat_type="private",
    user_id=ADMIN_ID,
    content=NETSCAPE_CONTENT.encode(),
):
    """Build (update, context) mocks for handle_cookie_document."""
    update = MagicMock()
    update.effective_chat.type = chat_type
    update.message.chat.type = chat_type
    update.message.from_user.id = user_id
    update.message.from_user.first_name = "Admin"
    update.message.from_user.username = "adminuser"
    update.message.caption = caption
    update.message.document = MagicMock()
    update.message.document.file_name = filename
    update.message.document.file_id = "file123"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(content))
    context.bot.get_file = AsyncMock(return_value=tg_file)
    return update, context


@pytest.fixture
def cookie_env(tmp_path):
    """Isolated cookie paths + bot admin allowlist."""
    cookies_dir = tmp_path / "cookies"
    paths = {
        "ig": str(tmp_path / "ig-cookies.txt"),
        "tt": str(tmp_path / "tiktok-cookies.txt"),
        "yt": str(cookies_dir / "yt-cookies.txt"),
    }
    with patch("cookie_upload.COOKIES_DIR", str(cookies_dir)), \
         patch("cookie_upload.IG_COOKIES_PATH", paths["ig"]), \
         patch("cookie_upload.TIKTOK_COOKIES_PATH", paths["tt"]), \
         patch("cookie_upload.YT_COOKIES_PATH", paths["yt"]), \
         patch("auth.BOT_ADMIN_IDS", {ADMIN_ID}):
        yield {**paths, "dir": str(cookies_dir)}


def _assert_no_side_effects(update, context):
    update.message.reply_text.assert_not_called()
    context.bot.get_file.assert_not_called()


class TestAccessControl:
    @pytest.mark.asyncio
    async def test_group_chat_silently_ignored(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(
            caption="cookie update tt", chat_type="supergroup", user_id=ADMIN_ID
        )
        with patch("cookie_upload.log_cookie_updated") as mock_log:
            await handle_cookie_document(update, context)
        _assert_no_side_effects(update, context)
        mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_admin_private_chat_silently_ignored(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update tt", user_id=OTHER_ID)
        with patch("cookie_upload.log_cookie_updated") as mock_log:
            await handle_cookie_document(update, context)
        _assert_no_side_effects(update, context)
        mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_admin_with_bad_caption_also_silent(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption=None, user_id=OTHER_ID)
        await handle_cookie_document(update, context)
        _assert_no_side_effects(update, context)


class TestCaptionValidation:
    @pytest.mark.asyncio
    async def test_missing_caption_prompts_reply_with_phrase(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption=None)
        await handle_cookie_document(update, context)
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_NO_CAPTION_HINT
        # file is accepted but NOT saved until the reply activates it
        assert not Path(cookie_env["ig"]).exists()
        assert not Path(cookie_env["tt"]).exists()

    @pytest.mark.asyncio
    async def test_whitespace_caption_treated_as_missing(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="   ")
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_NO_CAPTION_HINT

    @pytest.mark.asyncio
    async def test_wrong_keyword_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="update cookies tt")
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_CAPTION

    @pytest.mark.asyncio
    async def test_platform_uppercase_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update TT")
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_CAPTION

    @pytest.mark.asyncio
    async def test_unknown_platform_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update xx")
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_CAPTION

    @pytest.mark.asyncio
    async def test_extra_text_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update tt please")
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_CAPTION

    @pytest.mark.asyncio
    async def test_keyword_prefix_case_insensitive(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="CoOkIe UpDaTe tt")
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_document(update, context)
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[0][0].startswith(
            MSG_COOKIE_UPDATED.format(platform="tt")
        )


class TestFileValidation:
    @pytest.mark.asyncio
    async def test_non_txt_extension_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update tt", filename="cookies.pdf")
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_FILE

    @pytest.mark.asyncio
    async def test_non_cookie_content_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(
            caption="cookie update tt", content=b"just some text\nnot cookies\n"
        )
        await handle_cookie_document(update, context)
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_FILE

    @pytest.mark.asyncio
    async def test_rejected_file_not_saved(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(
            caption="cookie update ig", content=b"garbage", filename="c.TXT"
        )
        await handle_cookie_document(update, context)
        assert not Path(cookie_env["ig"]).exists()


class TestSuccessfulUpload:
    @pytest.mark.asyncio
    async def test_ig_upload_writes_dated_and_active_files(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update ig")
        with patch("cookie_upload.log_cookie_updated") as mock_log:
            await handle_cookie_document(update, context)

        today = datetime.date.today().isoformat()
        dated = Path(cookie_env["dir"]) / f"ig-cookie-{today}.txt"
        assert dated.exists()
        assert Path(cookie_env["ig"]).exists()
        assert dated.read_text() == NETSCAPE_CONTENT
        assert Path(cookie_env["ig"]).read_text() == NETSCAPE_CONTENT

        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[0][0].startswith(
            MSG_COOKIE_UPDATED.format(platform="ig")
        )
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_yt_upload_writes_yt_paths(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update yt")
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_document(update, context)

        today = datetime.date.today().isoformat()
        dated = Path(cookie_env["dir"]) / f"yt-cookie-{today}.txt"
        assert dated.exists()
        assert Path(cookie_env["yt"]).exists()

    @pytest.mark.asyncio
    async def test_tt_upload_writes_tt_paths(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update tt")
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_document(update, context)

        today = datetime.date.today().isoformat()
        dated = Path(cookie_env["dir"]) / f"tt-cookie-{today}.txt"
        assert dated.exists()
        assert Path(cookie_env["tt"]).exists()

    @pytest.mark.asyncio
    async def test_log_receives_platform_and_admin(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update, context = _make_update(caption="cookie update tt")
        with patch("cookie_upload.log_cookie_updated") as mock_log:
            await handle_cookie_document(update, context)

        args = mock_log.call_args[0]
        assert args[0] == "tt"
        assert args[1].id == ADMIN_ID

    @pytest.mark.asyncio
    async def test_same_day_reupload_overwrites(self, cookie_env):
        from cookie_upload import handle_cookie_document

        update1, context1 = _make_update(
            caption="cookie update tt", content=NETSCAPE_CONTENT.encode()
        )
        update2, context2 = _make_update(
            caption="cookie update tt", content=b"# Netscape HTTP Cookie File\n.new\tTRUE\t/\tTRUE\t0\tSID\tzzz\n"
        )
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_document(update1, context1)
            await handle_cookie_document(update2, context2)

        today = datetime.date.today().isoformat()
        dated = Path(cookie_env["dir"]) / f"tt-cookie-{today}.txt"
        assert "zzz" in dated.read_text()


class TestExpiryNote:
    @pytest.mark.asyncio
    async def test_reply_includes_expiry_note(self, cookie_env):
        from cookie_upload import handle_cookie_document
        from messages import MSG_COOKIE_UPDATED

        expiry_day = datetime.date.today() + datetime.timedelta(days=120)
        exp_ts = int(datetime.datetime.combine(expiry_day, datetime.time(12, 0)).timestamp())
        content = (
            "# Netscape HTTP Cookie File\n"
            f".instagram.com\tTRUE\t/\tTRUE\t{exp_ts}\tsessionid\tvalue\n"
        )
        update, context = _make_update(caption="cookie update ig", content=content.encode())
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_document(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert text.startswith(MSG_COOKIE_UPDATED.format(platform="ig"))
        assert "sessionid expires" in text
        assert expiry_day.isoformat() in text
        assert "120 days left" in text

    @pytest.mark.asyncio
    async def test_reply_warns_when_no_auth_cookie(self, cookie_env):
        from cookie_upload import handle_cookie_document
        from messages import MSG_COOKIE_NO_AUTH, MSG_COOKIE_UPDATED

        # SID is a YouTube cookie; on a `tt` upload there is no TT auth cookie
        update, context = _make_update(caption="cookie update tt")
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_document(update, context)

        text = update.message.reply_text.call_args[0][0]
        assert text.startswith(MSG_COOKIE_UPDATED.format(platform="tt"))
        assert MSG_COOKIE_NO_AUTH in text


def _make_reply_update(
    *,
    text="cookie update ig",
    filename="cookies.txt",
    content=NETSCAPE_CONTENT.encode(),
    chat_type="private",
    user_id=ADMIN_ID,
    has_document=True,
):
    """Build (update, context) mocks for a text reply to an uploaded file."""
    update = MagicMock()
    update.effective_chat.type = chat_type
    update.message.chat.type = chat_type
    update.message.from_user.id = user_id
    update.message.from_user.first_name = "Admin"
    update.message.message_id = 55
    update.message.text = text
    update.message.caption = None
    update.message.reply_text = AsyncMock()

    replied = MagicMock()
    if has_document:
        replied.document = MagicMock()
        replied.document.file_name = filename
        replied.document.file_id = "file456"
    else:
        replied.document = None
    update.message.reply_to_message = replied

    context = MagicMock()
    tg_file = MagicMock()
    tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(content))
    context.bot.get_file = AsyncMock(return_value=tg_file)
    return update, context


class TestReplyActivation:
    """A caption-less file is activated by replying `cookie update <platform>`."""

    def test_filter_matches_phrase_reply_to_document(self):
        from cookie_upload import cookie_reply_filter

        update, _ = _make_reply_update(text="cookie update ig")
        assert cookie_reply_filter.check_update(update) is True

    def test_filter_matches_capitalized_phrase(self):
        from cookie_upload import cookie_reply_filter

        update, _ = _make_reply_update(text="Cookie update ig")
        assert cookie_reply_filter.check_update(update) is True

    def test_filter_rejects_wrong_phrase(self):
        from cookie_upload import cookie_reply_filter

        update, _ = _make_reply_update(text="update cookies ig")
        assert cookie_reply_filter.check_update(update) is False

    def test_filter_rejects_phrase_without_document_reply(self):
        from cookie_upload import cookie_reply_filter

        update, _ = _make_reply_update(text="cookie update ig", has_document=False)
        assert cookie_reply_filter.check_update(update) is False

    def test_filter_rejects_phrase_without_reply_target(self):
        from cookie_upload import cookie_reply_filter

        update, _ = _make_reply_update(text="cookie update ig")
        update.message.reply_to_message = None
        assert cookie_reply_filter.check_update(update) is False

    @pytest.mark.asyncio
    async def test_reply_updates_cookies(self, cookie_env):
        from cookie_upload import handle_cookie_reply

        update, context = _make_reply_update(
            text="cookie update ig",
            content=(
                "# Netscape HTTP Cookie File\n"
                ".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\tabc\n"
            ).encode(),
        )
        with patch("cookie_upload.log_cookie_updated") as mock_log:
            await handle_cookie_reply(update, context)

        assert Path(cookie_env["ig"]).exists()
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[0][0].startswith(
            MSG_COOKIE_UPDATED.format(platform="ig")
        )
        mock_log.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_with_capitalized_phrase_updates_cookies(self, cookie_env):
        from cookie_upload import handle_cookie_reply

        update, context = _make_reply_update(text="Cookie update ig")
        with patch("cookie_upload.log_cookie_updated"):
            await handle_cookie_reply(update, context)
        assert Path(cookie_env["ig"]).exists()

    @pytest.mark.asyncio
    async def test_reply_to_non_txt_file_rejected(self, cookie_env):
        from cookie_upload import handle_cookie_reply

        update, context = _make_reply_update(filename="cookies.pdf")
        await handle_cookie_reply(update, context)
        update.message.reply_text.assert_called_once()
        assert update.message.reply_text.call_args[0][0] == MSG_COOKIE_INVALID_FILE
        assert not Path(cookie_env["ig"]).exists()

    @pytest.mark.asyncio
    async def test_reply_non_admin_silent(self, cookie_env):
        from cookie_upload import handle_cookie_reply

        update, context = _make_reply_update(user_id=OTHER_ID)
        await handle_cookie_reply(update, context)
        _assert_no_side_effects(update, context)

    @pytest.mark.asyncio
    async def test_reply_in_group_silent(self, cookie_env):
        from cookie_upload import handle_cookie_reply

        update, context = _make_reply_update(chat_type="supergroup")
        await handle_cookie_reply(update, context)
        _assert_no_side_effects(update, context)

    @pytest.mark.asyncio
    async def test_reply_to_message_without_document_silent(self, cookie_env):
        from cookie_upload import handle_cookie_reply

        update, context = _make_reply_update(has_document=False)
        await handle_cookie_reply(update, context)
        _assert_no_side_effects(update, context)


class TestServiceLog:
    def test_log_cookie_updated_writes_service_event(self):
        from logging_config import log_cookie_updated

        user = MagicMock()
        user.id = ADMIN_ID
        user.first_name = "Admin"
        user.username = "adminuser"

        with patch("logging_config.service_logger") as mock_logger:
            log_cookie_updated("tt", user, "tt-cookie-2026-10-28.txt")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "cookies_updated"
        log_data = call_args[1]["extra"]["extra_data"]
        assert log_data["event"] == "cookies_updated"
        assert log_data["platform"] == "tt"
        assert log_data["file"] == "tt-cookie-2026-10-28.txt"
        assert log_data["user"]["id"] == ADMIN_ID
        assert log_data["user"]["username"] == "adminuser"
