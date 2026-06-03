import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from commands import start_command, help_command, get_caption_for_user, caption_command, _user_caption_prefs


@pytest.fixture(autouse=True)
def clear_caption_prefs():
    """Clear caption preferences before each test to avoid cross-test pollution."""
    _user_caption_prefs.clear()
    yield
    _user_caption_prefs.clear()


# --- get_caption_for_user tests ---


def test_get_caption_for_user_default_no_preference():
    """Default (no entry in dict) = captions off, returns empty string."""
    result = get_caption_for_user(user_id=99999, title="My Video Title")
    assert result == ""


def test_get_caption_for_user_explicit_captions_on():
    """Explicit "on" preference (value False in dict) = captions on, returns title."""
    _user_caption_prefs[12345] = False
    result = get_caption_for_user(user_id=12345, title="My Video Title")
    assert result == "My Video Title"


def test_get_caption_for_user_explicit_captions_off():
    """Explicit "off" preference (value True in dict) = captions off, returns empty string."""
    _user_caption_prefs[12345] = True
    result = get_caption_for_user(user_id=12345, title="My Video Title")
    assert result == ""


def test_get_caption_for_user_title_truncation():
    """Title is truncated at 1024 characters."""
    _user_caption_prefs[100] = False
    long_title = "A" * 2000
    result = get_caption_for_user(user_id=100, title=long_title)
    assert len(result) == 1024
    assert result == "A" * 1024


def test_get_caption_for_user_title_exactly_1024():
    """Title exactly 1024 chars is not truncated."""
    _user_caption_prefs[100] = False
    title_1024 = "B" * 1024
    result = get_caption_for_user(user_id=100, title=title_1024)
    assert result == title_1024
    assert len(result) == 1024


def test_get_caption_for_user_empty_title():
    """Empty title returns empty string (no captions to show)."""
    _user_caption_prefs[100] = False
    result = get_caption_for_user(user_id=100, title="")
    assert result == ""


def test_get_caption_for_user_short_title():
    """Short title is returned unchanged when captions are on."""
    _user_caption_prefs[100] = False
    result = get_caption_for_user(user_id=100, title="Short")
    assert result == "Short"


def test_get_caption_for_user_independent_per_user():
    """Caption preferences are independent per user."""
    _user_caption_prefs[1] = False  # user 1: captions on
    _user_caption_prefs[2] = True   # user 2: captions off

    assert get_caption_for_user(1, "Video") == "Video"
    assert get_caption_for_user(2, "Video") == ""
    # user 3 has no preference -> default off
    assert get_caption_for_user(3, "Video") == ""


# --- caption_command tests ---


@pytest.fixture
def update():
    u = MagicMock()
    u.message = AsyncMock()
    u.message.from_user = MagicMock()
    u.message.from_user.id = 123456
    u.message.text = ""
    u.message.reply_text = AsyncMock()
    u.message.message_id = 42
    return u


@pytest.fixture
def context():
    ctx = MagicMock()
    ctx.user_data = {}
    return ctx


@pytest.mark.asyncio
async def test_caption_command_enables_captions(update, context):
    update.message.text = "/caption on"
    await caption_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Captions enabled" in text
    assert _user_caption_prefs[123456] is False


@pytest.mark.asyncio
async def test_caption_command_disables_captions(update, context):
    update.message.text = "/caption off"
    await caption_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Captions removed" in text
    assert _user_caption_prefs[123456] is True


@pytest.mark.asyncio
async def test_caption_command_shows_status_when_no_arg(update, context):
    update.message.text = "/caption"
    await caption_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Current caption setting" in text
    assert "OFF" in text  # default is off


@pytest.mark.asyncio
async def test_caption_command_shows_status_when_already_on(update, context):
    _user_caption_prefs[123456] = False  # captions on
    update.message.text = "/caption"
    await caption_command(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "ON" in text


@pytest.mark.asyncio
async def test_caption_command_accepts_numeric_aliases(update, context):
    """'1' enables, '0' disables, matching on/off behavior."""
    update.message.text = "/caption 1"
    await caption_command(update, context)
    assert _user_caption_prefs[123456] is False

    _user_caption_prefs.clear()
    update.message.text = "/caption 0"
    await caption_command(update, context)
    assert _user_caption_prefs[123456] is True


@pytest.mark.asyncio
async def test_caption_command_rejects_unauthorized_user(update, context):
    """Unauthorized user gets rejected."""
    with patch("commands.is_authorized", return_value=False):
        update.message.text = "/caption on"
        await caption_command(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "not authorized" in text
    # Preference should NOT be set
    assert 123456 not in _user_caption_prefs


@pytest.mark.asyncio
async def test_caption_command_includes_reply_parameters(update, context):
    """All replies include reply_parameters with message_id."""
    update.message.text = "/caption on"
    await caption_command(update, context)
    kwargs = update.message.reply_text.call_args[1]
    assert "reply_parameters" in kwargs
    assert kwargs["reply_parameters"] == {"message_id": 42}


# --- start_command tests ---


@pytest.mark.asyncio
async def test_start_command(update, context):
    """start_command sends welcome message with bot info."""
    context.bot_data = {"bot_username": "testbot"}
    await start_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Media Downloader Bot" in text


@pytest.mark.asyncio
async def test_start_command_logs_new_user(update, context):
    """start_command logs when a new user starts the bot."""
    context.bot_data = {"bot_username": "testbot"}
    with patch("commands.is_new_user", return_value=True) as mock_is_new, \
         patch("commands.log_new_user") as mock_log:
        await start_command(update, context)
        mock_is_new.assert_called_once_with(123456)
        mock_log.assert_called_once()


@pytest.mark.asyncio
async def test_start_command_does_not_log_returning_user(update, context):
    """start_command does not log when a returning user starts the bot."""
    context.bot_data = {"bot_username": "testbot"}
    with patch("commands.is_new_user", return_value=False) as mock_is_new, \
         patch("commands.log_new_user") as mock_log:
        await start_command(update, context)
        mock_is_new.assert_called_once_with(123456)
        mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_start_command_rejects_unauthorized_user(update, context):
    """Unauthorized user gets rejected by start_command."""
    with patch("commands.is_authorized", return_value=False):
        await start_command(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "not authorized" in text


# --- help_command tests ---


@pytest.mark.asyncio
async def test_help_command(update, context):
    """help_command sends supported platforms and commands."""
    await help_command(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "YouTube" in text
    assert "TikTok" in text
    assert "Instagram" in text


@pytest.mark.asyncio
async def test_help_command_rejects_unauthorized_user(update, context):
    """Unauthorized user gets rejected by help_command."""
    with patch("commands.is_authorized", return_value=False):
        await help_command(update, context)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "not authorized" in text
