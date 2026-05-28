import os
import tempfile
from unittest.mock import patch


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
