import os
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
