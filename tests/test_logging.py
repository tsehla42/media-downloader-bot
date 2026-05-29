import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


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


def test_log_request_completed_basic():
    """log_request_completed outputs JSON with all required fields."""
    from logging_config import log_request_completed

    with patch("logging_config.logging") as mock_logging:
        log_request_completed(
            request_id="a1b2c3d4",
            url="https://youtube.com/watch?v=abc",
            platform="youtube",
            duration_ms=15000,
            success=True,
            content_type="video",
            file_size_mb=45.2,
        )

        mock_logging.info.assert_called_once()
        call_args = mock_logging.info.call_args
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


def test_log_request_failed_basic():
    """log_request_failed outputs JSON with all required fields."""
    from logging_config import log_request_failed

    with patch("logging_config.logging") as mock_logging:
        log_request_failed(
            request_id="a1b2c3d4",
            url="https://youtube.com/watch?v=abc",
            platform="youtube",
            error="yt-dlp timeout",
            error_type="TimeoutError",
        )

        mock_logging.error.assert_called_once()
        call_args = mock_logging.error.call_args
        assert call_args[0][0] == "request_failed"
        log_data = call_args[1]["extra"]["extra_data"]

        assert log_data["event"] == "request_failed"
        assert log_data["message"] == "Request failed: yt-dlp timeout"
        assert log_data["request_id"] == "a1b2c3d4"
        assert log_data["url"] == "https://youtube.com/watch?v=abc"
        assert log_data["platform"] == "youtube"
        assert log_data["error"] == "yt-dlp timeout"
        assert log_data["error_type"] == "TimeoutError"


def test_decorator_generates_request_id():
    """Decorator generates UUID and stores in context.user_data."""
    from logging_config import with_request_logging

    mock_context = MagicMock()
    mock_context.user_data = {}
    mock_update = MagicMock()

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
    mock_update = MagicMock()

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
    mock_update = MagicMock()

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
    mock_update = MagicMock()

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
    mock_update = MagicMock()

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
    mock_update = MagicMock()

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
