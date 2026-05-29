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
    logging.info("media_request", extra={"extra_data": log_data})


def log_request_received(
    request_id: str,
    url: str,
    platform: str,
    user: object,
    chat: object,
) -> None:
    """Log when a request is received."""
    log_data = {
        "event": "request_received",
        "message": "Request received",
        "request_id": request_id,
        "url": url,
        "platform": platform,
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
    }
    logging.info("request_received", extra={"extra_data": log_data})


def log_request_completed(
    request_id: str,
    url: str,
    platform: str,
    duration_ms: int,
    success: bool,
    content_type: str | None = None,
    file_size_mb: float | None = None,
    error: str | None = None,
) -> None:
    """Log when a request completes (success or expected failure)."""
    log_data = {
        "event": "request_completed",
        "message": "Request completed",
        "request_id": request_id,
        "url": url,
        "platform": platform,
        "duration_ms": duration_ms,
        "success": success,
        "content_type": content_type,
        "file_size_mb": file_size_mb,
    }
    if error:
        log_data["error"] = error
    logging.info("request_completed", extra={"extra_data": log_data})


def log_request_failed(
    request_id: str,
    url: str,
    platform: str,
    error: str,
    error_type: str,
) -> None:
    """Log when a request fails with an exception."""
    log_data = {
        "event": "request_failed",
        "message": f"Request failed: {error}",
        "request_id": request_id,
        "url": url,
        "platform": platform,
        "error": error,
        "error_type": error_type,
    }
    logging.error("request_failed", extra={"extra_data": log_data})


def log_error(
    url: str,
    error: str,
    platform: str,
    user: object,
    chat: object,
) -> None:
    """Log an error with context."""
    log_data = {
        "event": "download_failed",
        "url": url,
        "error": error,
        "platform": platform,
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
    }
    logging.error("download_failed", extra={"extra_data": log_data})


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

        # Also write to dev log files (same structure as prod)
        os.makedirs(LOG_DIR, exist_ok=True)

        dev_request_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "requests.dev.jsonl"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        dev_request_handler.setFormatter(formatter)
        root.addHandler(dev_request_handler)

        dev_error_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "errors.dev.jsonl"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        dev_error_handler.setLevel(logging.ERROR)
        dev_error_handler.setFormatter(formatter)
        root.addHandler(dev_error_handler)
