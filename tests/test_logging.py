import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _clean_logging():
    """Reset logging state between tests."""
    import logging
    import logging_config

    logging_config._initialized = False
    root = logging.getLogger()
    root.handlers.clear()
    yield
    logging_config._initialized = False
    root.handlers.clear()


def test_config_default_log_output():
    """LOG_OUTPUT defaults to 'both'."""
    with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
        import importlib
        import config
        importlib.reload(config)
        assert config.LOG_OUTPUT == "both"


def test_config_default_mode():
    """MODE defaults to 'development'."""
    with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
        import importlib
        import config
        importlib.reload(config)
        assert config.MODE == "development"


def test_config_default_log_dir():
    """LOG_DIR defaults to 'logs'."""
    with patch.dict(os.environ, {}, clear=True), patch("dotenv.load_dotenv"):
        import importlib
        import config
        importlib.reload(config)
        assert config.LOG_DIR == "logs"


def test_config_custom_log_output():
    """LOG_OUTPUT can be set to 'file'."""
    with patch.dict(os.environ, {"LOG_OUTPUT": "file"}):
        import importlib
        import config
        importlib.reload(config)
        assert config.LOG_OUTPUT == "file"


def test_config_custom_mode():
    """MODE can be set to 'production'."""
    with patch.dict(os.environ, {"MODE": "production"}):
        import importlib
        import config
        importlib.reload(config)
        assert config.MODE == "production"


def test_config_custom_log_dir():
    """LOG_DIR can be set to a custom path."""
    with patch.dict(os.environ, {"LOG_DIR": "/var/log/bot"}):
        import importlib
        import config
        importlib.reload(config)
        assert config.LOG_DIR == "/var/log/bot"


import json
import logging
import logging.handlers
from datetime import datetime, timezone, timedelta


def test_json_formatter_basic():
    """JSONFormatter outputs valid JSON with required fields."""
    from logging_config import JSONFormatter

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="test message",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert "timestamp" in data
    assert data["level"] == "INFO"
    assert data["message"] == "test message"


def test_json_formatter_with_extra():
    """JSONFormatter includes extra_data from log record."""
    from logging_config import JSONFormatter

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="test",
        args=(),
        exc_info=None,
    )
    record.extra_data = {"url": "https://example.com", "platform": "youtube"}
    output = formatter.format(record)
    data = json.loads(output)

    assert data["url"] == "https://example.com"
    assert data["platform"] == "youtube"


def test_json_formatter_timestamp_format():
    """Timestamp is ISO 8601 format with timezone offset (Kyiv: UTC+2/+3)."""
    from logging_config import JSONFormatter

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="test",
        args=(),
        exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)

    # Parse timestamp to verify format
    ts = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
    # Kyiv timezone: UTC+2 (winter) or UTC+3 (summer)
    assert ts.tzinfo is not None
    offset = ts.tzinfo.utcoffset(ts)
    assert offset in (timezone(timedelta(hours=2)).utcoffset(ts),
                      timezone(timedelta(hours=3)).utcoffset(ts))


def test_setup_logging_console_only():
    """setup_logging configures console handler when LOG_OUTPUT=console."""
    import importlib

    import config
    from logging_config import setup_logging

    with patch.dict(os.environ, {"LOG_OUTPUT": "console"}):
        importlib.reload(config)
        setup_logging()

    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(stream_handlers) >= 1
    assert len(file_handlers) == 0


def test_setup_logging_file_only():
    """setup_logging configures file handler when LOG_OUTPUT=file."""
    import importlib

    import config
    from logging_config import setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "production"}):
            importlib.reload(config)
            setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        # Exclude pytest's LogCaptureHandler (subclass of StreamHandler)
        our_stream = [h for h in root.handlers
                      if isinstance(h, logging.StreamHandler)
                      and type(h) is logging.StreamHandler]
        assert len(file_handlers) >= 1
        assert len(our_stream) == 0

        assert os.path.exists(os.path.join(tmpdir, "requests.jsonl"))


def test_setup_logging_both():
    """setup_logging configures both console and file when LOG_OUTPUT=both."""
    import importlib

    import config
    from logging_config import setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "both", "LOG_DIR": tmpdir, "MODE": "production"}):
            importlib.reload(config)
            setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
        assert len(file_handlers) >= 1
        assert len(stream_handlers) >= 1

        assert os.path.exists(os.path.join(tmpdir, "requests.jsonl"))


def test_setup_logging_stdout_alias():
    """setup_logging treats LOG_OUTPUT=stdout as console."""
    import importlib

    import config
    from logging_config import setup_logging

    with patch.dict(os.environ, {"LOG_OUTPUT": "stdout"}):
        importlib.reload(config)
        setup_logging()

    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(stream_handlers) >= 1
    assert len(file_handlers) == 0


def test_setup_logging_development_log_file():
    """MODE=dev produces requests.dev.jsonl."""
    import importlib

    import config
    from logging_config import setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "dev"}):
            importlib.reload(config)
            setup_logging()

        assert os.path.exists(os.path.join(tmpdir, "requests.dev.jsonl"))
        assert not os.path.exists(os.path.join(tmpdir, "requests.jsonl"))


def test_setup_logging_production_log_file():
    """MODE=prod produces requests.jsonl."""
    import importlib

    import config
    from logging_config import setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "prod"}):
            importlib.reload(config)
            setup_logging()

        assert os.path.exists(os.path.join(tmpdir, "requests.jsonl"))
        assert not os.path.exists(os.path.join(tmpdir, "requests.dev.jsonl"))


def test_setup_logging_idempotent():
    """setup_logging can be called multiple times without duplicate handlers."""
    import importlib

    import config
    from logging_config import setup_logging

    with patch.dict(os.environ, {"LOG_OUTPUT": "console"}):
        importlib.reload(config)
        setup_logging()
        handler_count = len(logging.getLogger().handlers)
        setup_logging()
        # Should not double handlers
        assert len(logging.getLogger().handlers) == handler_count


def test_log_request_received_omits_platform():
    """log_request_received does not include platform field."""
    from logging_config import log_request_received

    user = MagicMock()
    user.id = 123
    user.first_name = "Test"
    user.username = "test"

    chat = MagicMock()
    chat.id = -100
    chat.title = "Group"
    chat.type = "group"

    with patch("logging_config.requests_logger") as mock_logger:
        log_request_received(
            request_id="abc123",
            url="https://example.com",
            user=user,
            chat=chat,
        )
        log_data = mock_logger.info.call_args[1]["extra"]["extra_data"]
        assert "platform" not in log_data
        assert log_data["user"]["id"] == 123
        assert log_data["chat"]["id"] == -100


def test_log_request_completed_includes_user_and_chat():
    """log_request_completed includes user and chat fields."""
    from logging_config import log_request_completed

    user = MagicMock()
    user.id = 123
    user.first_name = "Test"
    user.username = "test"

    chat = MagicMock()
    chat.id = -100
    chat.title = "Group"
    chat.type = "group"

    with patch("logging_config.requests_logger") as mock_logger:
        log_request_completed(
            request_id="abc123",
            url="https://example.com",
            platform="youtube",
            duration_ms=5000,
            success=True,
            content_type="video",
            file_size_mb=10.5,
            user=user,
            chat=chat,
        )
        log_data = mock_logger.info.call_args[1]["extra"]["extra_data"]
        assert log_data["user"]["id"] == 123
        assert log_data["chat"]["id"] == -100
        assert log_data["platform"] == "youtube"


def test_log_request_failed_includes_user_and_chat():
    """log_request_failed includes user and chat fields."""
    from logging_config import log_request_failed

    user = MagicMock()
    user.id = 123
    user.first_name = "Test"
    user.username = "test"

    chat = MagicMock()
    chat.id = -100
    chat.title = "Group"
    chat.type = "group"

    with patch("logging_config.requests_logger") as mock_logger:
        log_request_failed(
            request_id="abc123",
            url="https://example.com",
            platform="youtube",
            error="timeout",
            error_type="TimeoutError",
            user=user,
            chat=chat,
        )
        log_data = mock_logger.error.call_args[1]["extra"]["extra_data"]
        assert log_data["user"]["id"] == 123
        assert log_data["chat"]["id"] == -100


def test_log_request_received_basic():
    """log_request_received outputs JSON with all required fields."""
    from logging_config import log_request_received

    user = MagicMock()
    user.id = 123456
    user.first_name = "Test"
    user.username = "testuser"

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "group"

    with patch("logging_config.requests_logger") as mock_logger:
        log_request_received(
            request_id="a1b2c3d4",
            url="https://youtube.com/watch?v=abc",
            user=user,
            chat=chat,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "request_received"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "request_received"
        assert log_data["message"] == "Request received"
        assert log_data["request_id"] == "a1b2c3d4"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert "platform" not in log_data
        assert log_data["user"]["id"] == 123456
        assert log_data["user"]["name"] == "Test"
        assert log_data["user"]["username"] == "testuser"
        assert log_data["chat"]["id"] == -100789
        assert log_data["chat"]["name"] == "Test Group"
        assert log_data["chat"]["type"] == "group"


def test_log_request_completed_basic():
    """log_request_completed outputs JSON with all required fields."""
    from logging_config import log_request_completed

    user = MagicMock()
    user.id = 123456
    user.first_name = "Test"
    user.username = "testuser"

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "group"

    with patch("logging_config.requests_logger") as mock_logger:
        log_request_completed(
            request_id="a1b2c3d4",
            url="https://youtube.com/watch?v=abc",
            platform="youtube",
            duration_ms=15000,
            success=True,
            content_type="video",
            file_size_mb=45.2,
            user=user,
            chat=chat,
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "request_completed"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "request_completed"
        assert log_data["message"] == "Request completed"
        assert log_data["request_id"] == "a1b2c3d4"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert log_data["platform"] == "youtube"
        assert log_data["duration_ms"] == 15000
        assert log_data["success"] is True
        assert log_data["content_type"] == "video"
        assert log_data["file_size_mb"] == 45.2
        assert log_data["user"]["id"] == 123456
        assert log_data["chat"]["id"] == -100789


def test_log_request_failed_basic():
    """log_request_failed outputs JSON with all required fields."""
    from logging_config import log_request_failed

    user = MagicMock()
    user.id = 123456
    user.first_name = "Test"
    user.username = "testuser"

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "group"

    with patch("logging_config.requests_logger") as mock_logger:
        log_request_failed(
            request_id="a1b2c3d4",
            url="https://youtube.com/watch?v=abc",
            platform="youtube",
            error="yt-dlp timeout",
            error_type="TimeoutError",
            user=user,
            chat=chat,
        )

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert call_args[0][0] == "request_failed"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "request_failed"
        assert log_data["message"] == "Request failed: yt-dlp timeout"
        assert log_data["request_id"] == "a1b2c3d4"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert log_data["platform"] == "youtube"
        assert log_data["error"] == "yt-dlp timeout"
        assert log_data["error_type"] == "TimeoutError"
        assert log_data["user"]["id"] == 123456
        assert log_data["chat"]["id"] == -100789


def _make_update_with_url(url="https://youtube.com/watch?v=abc"):
    """Create a mock update with a valid URL in message text."""
    mock_update = MagicMock()
    mock_update.message.text = url
    mock_update.callback_query = None
    return mock_update


def test_decorator_generates_request_id():
    """Decorator generates UUID and stores in context.user_data."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = _make_update_with_url()

    @with_request_logging
    async def dummy_handler(update, context):
        return "success"

    with patch("logging_config.logging"):
        import asyncio
        result = asyncio.run(dummy_handler(mock_update, mock_context))

    assert "request_id" in mock_context.user_data
    assert len(mock_context.user_data["request_id"]) == 8
    assert result == "success"


def test_decorator_logs_request_received():
    """Decorator calls log_request_received at handler start."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = _make_update_with_url()

    @with_request_logging
    async def dummy_handler(update, context):
        return "success"

    with patch("logging_config.log_request_received") as mock_received:
        import asyncio
        asyncio.run(dummy_handler(mock_update, mock_context))

    mock_received.assert_called_once()
    call_args = mock_received.call_args
    assert call_args[1]["request_id"] == mock_context.user_data["request_id"]


def test_decorator_logs_request_completed():
    """Decorator calls log_request_completed on success."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = _make_update_with_url()

    @with_request_logging
    async def dummy_handler(update, context):
        return "success"

    with patch("logging_config.log_request_completed") as mock_completed:
        import asyncio
        asyncio.run(dummy_handler(mock_update, mock_context))

    mock_completed.assert_called_once()
    call_args = mock_completed.call_args
    assert call_args[1]["request_id"] == mock_context.user_data["request_id"]
    assert call_args[1]["success"] is True


def test_decorator_logs_request_failed():
    """Decorator calls log_request_failed on exception."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = _make_update_with_url()

    @with_request_logging
    async def dummy_handler(update, context):
        raise ValueError("test error")

    with patch("logging_config.log_request_failed") as mock_failed:
        import asyncio
        with pytest.raises(ValueError, match="test error"):
            asyncio.run(dummy_handler(mock_update, mock_context))

    mock_failed.assert_called_once()
    call_args = mock_failed.call_args
    assert call_args[1]["request_id"] == mock_context.user_data["request_id"]
    assert call_args[1]["error"] == "test error"
    assert call_args[1]["error_type"] == "ValueError"


def test_decorator_reraises_exception():
    """Decorator re-raises exception after logging."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = _make_update_with_url()

    @with_request_logging
    async def dummy_handler(update, context):
        raise RuntimeError("boom")

    with patch("logging_config.log_request_failed"):
        import asyncio
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(dummy_handler(mock_update, mock_context))


def test_decorator_calculates_duration():
    """Decorator calculates duration_ms correctly."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = _make_update_with_url()

    @with_request_logging
    async def dummy_handler(update, context):
        await asyncio.sleep(0.1)  # 100ms
        return "success"

    with patch("logging_config.log_request_completed") as mock_completed:
        import asyncio
        asyncio.run(dummy_handler(mock_update, mock_context))

    call_args = mock_completed.call_args
    duration_ms = call_args[1]["duration_ms"]
    assert duration_ms >= 90  # Allow some tolerance
    assert duration_ms <= 200


def test_is_new_user_returns_true_for_new_user():
    """is_new_user returns True for a user not seen before."""
    from logging_config import is_new_user
    import tempfile
    import os

    # Reset state
    import logging_config
    logging_config._seen_users = set()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "seen_users.json")
        with patch.object(logging_config, "_seen_users_file", test_file):
            result = is_new_user(12345)
            assert result is True
            # Should be marked as seen now
            assert 12345 in logging_config._seen_users


def test_is_new_user_returns_false_for_seen_user():
    """is_new_user returns False for a user already seen."""
    from logging_config import is_new_user
    import tempfile
    import os

    import logging_config
    logging_config._seen_users = set()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "seen_users.json")
        with patch.object(logging_config, "_seen_users_file", test_file):
            # First call - new user
            is_new_user(12345)
            # Second call - same user
            result = is_new_user(12345)
            assert result is False


def test_seen_users_persists_to_file():
    """Seen users are saved to file and loaded on next access."""
    from logging_config import is_new_user, _load_seen_users
    import tempfile
    import os
    import json

    import logging_config
    logging_config._seen_users = set()

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "seen_users.json")
        with patch.object(logging_config, "_seen_users_file", test_file):
            is_new_user(111)
            is_new_user(222)

            # Verify file was written
            assert os.path.exists(test_file)
            with open(test_file, "r") as f:
                data = json.load(f)
            assert 111 in data["user_ids"]
            assert 222 in data["user_ids"]

            # Reset in-memory cache and reload
            logging_config._seen_users = set()
            loaded = _load_seen_users()
            assert 111 in loaded
            assert 222 in loaded


def test_log_new_user_basic():
    """log_new_user outputs JSON with all required fields."""
    from logging_config import log_new_user

    user = MagicMock()
    user.id = 123456
    user.first_name = "Test"
    user.username = "testuser"

    with patch("logging_config.service_logger") as mock_logger:
        log_new_user(user)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "new_user_started"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "new_user_started"
        assert log_data["message"] == "New user started bot"
        assert log_data["user"]["id"] == 123456
        assert log_data["user"]["name"] == "Test"
        assert log_data["user"]["username"] == "testuser"


def test_log_bot_added_to_chat_basic():
    """log_bot_added_to_chat outputs JSON with all required fields."""
    from logging_config import log_bot_added_to_chat

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "supergroup"

    added_by = MagicMock()
    added_by.id = 123456
    added_by.first_name = "Admin"
    added_by.username = "admin"

    with patch("logging_config.service_logger") as mock_logger:
        log_bot_added_to_chat(chat, added_by)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "bot_added_to_chat"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "bot_added_to_chat"
        assert log_data["message"] == "Bot added to chat"
        assert log_data["chat"]["id"] == -100789
        assert log_data["chat"]["name"] == "Test Group"
        assert log_data["chat"]["type"] == "supergroup"
        assert log_data["added_by"]["id"] == 123456
        assert log_data["added_by"]["name"] == "Admin"
        assert log_data["added_by"]["username"] == "admin"


def test_log_bot_removed_from_chat_basic():
    """log_bot_removed_from_chat outputs JSON with all required fields."""
    from logging_config import log_bot_removed_from_chat

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "group"

    removed_by = MagicMock()
    removed_by.id = 123456
    removed_by.first_name = "Admin"
    removed_by.username = "admin"

    with patch("logging_config.service_logger") as mock_logger:
        log_bot_removed_from_chat(chat, removed_by)

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "bot_removed_from_chat"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "bot_removed_from_chat"
        assert log_data["message"] == "Bot removed from chat"
        assert log_data["chat"]["id"] == -100789
        assert log_data["removed_by"]["id"] == 123456


def test_log_bot_status_changed_basic():
    """log_bot_status_changed outputs JSON with all required fields."""
    from logging_config import log_bot_status_changed

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "supergroup"

    user = MagicMock()
    user.id = 123456
    user.first_name = "Admin"
    user.username = "admin"

    with patch("logging_config.service_logger") as mock_logger:
        log_bot_status_changed(chat, user, "member", "administrator")

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "bot_status_changed"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "bot_status_changed"
        assert log_data["message"] == "Bot status changed from member to administrator"
        assert log_data["old_status"] == "member"
        assert log_data["new_status"] == "administrator"
        assert log_data["user"]["id"] == 123456


def test_requests_filter_accepts_requests_logger():
    """RequestsFilter accepts records from media_downloader.requests logger."""
    from logging_config import RequestsFilter
    import logging

    f = RequestsFilter()
    record = logging.LogRecord(
        name="media_downloader.requests", level=logging.INFO,
        pathname="test.py", lineno=1, msg="test", args=(), exc_info=None,
    )
    assert f.filter(record) is True


def test_requests_filter_rejects_details_logger():
    """RequestsFilter rejects records from media_downloader.details logger."""
    from logging_config import RequestsFilter
    import logging

    f = RequestsFilter()
    record = logging.LogRecord(
        name="media_downloader.details", level=logging.INFO,
        pathname="test.py", lineno=1, msg="test", args=(), exc_info=None,
    )
    assert f.filter(record) is False


def test_details_filter_accepts_details_logger():
    """DetailsFilter accepts records from media_downloader.details logger."""
    from logging_config import DetailsFilter
    import logging

    f = DetailsFilter()
    record = logging.LogRecord(
        name="media_downloader.details", level=logging.INFO,
        pathname="test.py", lineno=1, msg="test", args=(), exc_info=None,
    )
    assert f.filter(record) is True


def test_details_filter_rejects_requests_logger():
    """DetailsFilter rejects records from media_downloader.requests logger."""
    from logging_config import DetailsFilter
    import logging

    f = DetailsFilter()
    record = logging.LogRecord(
        name="media_downloader.requests", level=logging.INFO,
        pathname="test.py", lineno=1, msg="test", args=(), exc_info=None,
    )
    assert f.filter(record) is False


def test_setup_logging_creates_two_file_handlers():
    """setup_logging creates separate file handlers for requests and details."""
    import importlib
    import config
    from logging_config import setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "production"}):
            importlib.reload(config)
            setup_logging()

        assert os.path.exists(os.path.join(tmpdir, "requests.jsonl"))
        assert os.path.exists(os.path.join(tmpdir, "request-details.jsonl"))


def test_setup_logging_development_creates_two_files():
    """MODE=dev creates requests.dev.jsonl and request-details.dev.jsonl."""
    import importlib
    import config
    from logging_config import setup_logging

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "dev"}):
            importlib.reload(config)
            setup_logging()

        assert os.path.exists(os.path.join(tmpdir, "requests.dev.jsonl"))
        assert os.path.exists(os.path.join(tmpdir, "request-details.dev.jsonl"))


def test_setup_logging_requests_filter_on_file_handler():
    """Requests file handler has RequestsFilter applied."""
    import importlib
    import config
    from logging_config import setup_logging, RequestsFilter

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "production"}):
            importlib.reload(config)
            setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        requests_handlers = [h for h in file_handlers if any(isinstance(f, RequestsFilter) for f in h.filters)]
        assert len(requests_handlers) == 1


def test_setup_logging_details_filter_on_file_handler():
    """Details file handler has DetailsFilter applied."""
    import importlib
    import config
    from logging_config import setup_logging, DetailsFilter

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir, "MODE": "production"}):
            importlib.reload(config)
            setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        details_handlers = [h for h in file_handlers if any(isinstance(f, DetailsFilter) for f in h.filters)]
        assert len(details_handlers) == 1


def test_reply_to_retry_logs_request_received():
    """Reply-to-retry branch calls log_request_received with structured data."""
    from unittest.mock import AsyncMock
    from handlers import handle_url

    update = MagicMock()
    update.message.text = "@bot retry"
    update.message.message_id = 1
    update.message.from_user = MagicMock()
    update.message.from_user.id = 123
    update.message.from_user.first_name = "Test"
    update.message.from_user.username = "test"
    update.message.chat = MagicMock()
    update.message.chat.id = -100
    update.message.chat.title = "Group"
    update.message.chat.type = "group"
    update.message.reply_to_message = MagicMock()
    update.message.reply_to_message.text = "https://tiktok.com/@user/video/123"
    update.message.reply_to_message.message_id = 2

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"bot_username": "bot"}

    with patch("handlers.log_request_received") as mock_received, \
         patch("handlers.log_request_completed") as mock_completed, \
         patch("handlers._download_and_send", new_callable=AsyncMock, return_value=True), \
         patch("handlers.is_authorized", return_value=True), \
         patch("handlers.typing_indicator") as mock_typing:
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_typing.return_value = mock_cm
        import asyncio
        asyncio.run(handle_url(update, context))

    mock_received.assert_called_once()
    call_args = mock_received.call_args[1]
    assert call_args["url"] == "https://tiktok.com/@user/video/123"
    assert call_args["user"].id == 123
    assert call_args["chat"].id == -100
