import os
import tempfile
from unittest.mock import MagicMock, patch


def test_config_default_log_output():
    """LOG_OUTPUT defaults to 'stdout'."""
    with patch.dict(os.environ, {}, clear=True):
        # Reimport to get fresh defaults
        import importlib
        import config
        importlib.reload(config)
        assert config.LOG_OUTPUT == "stdout"


def test_config_default_log_dir():
    """LOG_DIR defaults to 'logs'."""
    with patch.dict(os.environ, {}, clear=True):
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
from datetime import datetime, timezone


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
    """Timestamp is ISO 8601 UTC format."""
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
    assert ts.tzinfo == timezone.utc


def test_setup_logging_stdout():
    """setup_logging configures stdout handler when LOG_OUTPUT=stdout."""
    import importlib

    import config
    import logging_config
    from logging_config import setup_logging

    logging_config._initialized = False

    with patch.dict(os.environ, {"LOG_OUTPUT": "stdout"}):
        importlib.reload(config)
        setup_logging()

    root = logging.getLogger()
    stream_handlers = [h for h in root.handlers if isinstance(h, logging.StreamHandler)]
    assert len(stream_handlers) >= 1


def test_setup_logging_file():
    """setup_logging configures file handlers when LOG_OUTPUT=file."""
    import importlib

    import config
    import logging_config
    from logging_config import setup_logging

    logging_config._initialized = False

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"LOG_OUTPUT": "file", "LOG_DIR": tmpdir}):
            importlib.reload(config)
            setup_logging()

        root = logging.getLogger()
        file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(file_handlers) >= 2  # requests + errors

        # Check files were created
        assert os.path.exists(os.path.join(tmpdir, "requests.jsonl"))
        assert os.path.exists(os.path.join(tmpdir, "errors.jsonl"))


def test_setup_logging_idempotent():
    """setup_logging can be called multiple times without duplicate handlers."""
    import importlib

    import config
    import logging_config
    from logging_config import setup_logging

    logging_config._initialized = False

    with patch.dict(os.environ, {"LOG_OUTPUT": "stdout"}):
        importlib.reload(config)
        setup_logging()
        handler_count = len(logging.getLogger().handlers)
        setup_logging()
        # Should not double handlers
        assert len(logging.getLogger().handlers) == handler_count


def test_log_request_basic():
    """log_request outputs JSON with all required fields."""
    from logging_config import log_request

    user = MagicMock()
    user.id = 123456
    user.first_name = "Test"
    user.username = "testuser"

    chat = MagicMock()
    chat.id = -100789
    chat.title = "Test Group"
    chat.type = "group"

    with patch("logging_config.logging") as mock_logging:
        log_request(
            url="https://youtube.com/watch?v=abc",
            platform="youtube",
            content_type="video",
            user=user,
            chat=chat,
            media_info={
                "duration_seconds": 120,
                "file_size_mb": 45.2,
                "image_count": None,
                "quality": "720p",
            },
        )

        mock_logging.info.assert_called_once()
        call_args = mock_logging.info.call_args
        assert call_args[0][0] == "media_request"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "media_request"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert log_data["platform"] == "youtube"
        assert log_data["content_type"] == "video"
        assert log_data["user"]["id"] == 123456
        assert log_data["user"]["name"] == "Test"
        assert log_data["user"]["username"] == "testuser"
        assert log_data["chat"]["id"] == -100789
        assert log_data["chat"]["name"] == "Test Group"
        assert log_data["chat"]["type"] == "group"
        assert log_data["media"]["duration_seconds"] == 120
        assert log_data["media"]["file_size_mb"] == 45.2
        assert log_data["media"]["image_count"] is None
        assert log_data["media"]["quality"] == "720p"


def test_log_request_null_fields():
    """log_request handles null user/chat fields."""
    from logging_config import log_request

    user = MagicMock()
    user.id = 123
    user.first_name = None
    user.username = None

    chat = MagicMock()
    chat.id = 123
    chat.title = None
    chat.type = "private"

    with patch("logging_config.logging") as mock_logging:
        log_request(
            url="https://tiktok.com/video/123",
            platform="tiktok",
            content_type="image",
            user=user,
            chat=chat,
            media_info={
                "duration_seconds": None,
                "file_size_mb": 3.2,
                "image_count": 1,
                "quality": None,
            },
        )

        call_args = mock_logging.info.call_args
        assert call_args[0][0] == "media_request"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["user"]["name"] is None
        assert log_data["user"]["username"] is None
        assert log_data["chat"]["name"] is None
        assert log_data["media"]["image_count"] == 1


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

    with patch("logging_config.logging") as mock_logging:
        log_request_received(
            request_id="a1b2c3d4",
            url="https://youtube.com/watch?v=abc",
            platform="youtube",
            user=user,
            chat=chat,
        )

        mock_logging.info.assert_called_once()
        call_args = mock_logging.info.call_args
        assert call_args[0][0] == "request_received"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "request_received"
        assert log_data["message"] == "Request received"
        assert log_data["request_id"] == "a1b2c3d4"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert log_data["platform"] == "youtube"
        assert log_data["user"]["id"] == 123456
        assert log_data["user"]["name"] == "Test"
        assert log_data["user"]["username"] == "testuser"
        assert log_data["chat"]["id"] == -100789
        assert log_data["chat"]["name"] == "Test Group"
        assert log_data["chat"]["type"] == "group"


def test_log_error():
    """log_error outputs JSON with error details."""
    from logging_config import log_error

    user = MagicMock()
    user.id = 123
    user.first_name = "Test"
    user.username = "test"

    chat = MagicMock()
    chat.id = -100
    chat.title = "Group"
    chat.type = "group"

    with patch("logging_config.logging") as mock_logging:
        log_error(
            url="https://youtube.com/watch?v=abc",
            error="yt-dlp timeout",
            platform="youtube",
            user=user,
            chat=chat,
        )

        mock_logging.error.assert_called_once()
        call_args = mock_logging.error.call_args
        assert call_args[0][0] == "download_failed"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "download_failed"
        assert log_data["error"] == "yt-dlp timeout"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert log_data["platform"] == "youtube"
        assert log_data["user"]["id"] == 123
        assert log_data["chat"]["id"] == -100
