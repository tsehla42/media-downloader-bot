import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Include extra_data if present
        extra = getattr(record, "extra_data", {})
        log_data.update(extra)

        return json.dumps(log_data)


def log_request(
    url: str,
    platform: str,
    content_type: str,
    user: object,
    chat: object,
    media_info: dict,
) -> None:
    """Log a media request with structured data."""
    log_data = {
        "event": "media_request",
        "url": url,
        "platform": platform,
        "content_type": content_type,
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
        "chat": {
            "id": chat.id,
            "name": getattr(chat, "title", None),
            "type": getattr(chat, "type", None),
        },
        "media": media_info,
    }
    logging.info(json.dumps(log_data))


# Track if setup_logging has been called
_initialized = False


def setup_logging() -> None:
    """Configure logging based on LOG_OUTPUT environment variable."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    from config import LOG_OUTPUT, LOG_DIR

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    formatter = JSONFormatter()

    if LOG_OUTPUT == "file":
        os.makedirs(LOG_DIR, exist_ok=True)

        # Requests log - all levels
        request_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "requests.jsonl"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        request_handler.setFormatter(formatter)
        root.addHandler(request_handler)

        # Errors log - errors only
        error_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "errors.jsonl"),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root.addHandler(error_handler)

        # Also log errors to stderr
        stderr_handler = logging.StreamHandler()
        stderr_handler.setLevel(logging.ERROR)
        stderr_handler.setFormatter(formatter)
        root.addHandler(stderr_handler)
    else:
        # Stdout mode
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
