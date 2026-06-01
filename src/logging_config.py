import functools
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler

# Kyiv timezone: UTC+2 (winter) / UTC+3 (summer, EEST)
# Python's datetime doesn't have native DST support without zoneinfo,
# so we use a fixed offset that we toggle via env var or auto-detect.
# For simplicity, use the zoneinfo library (Python 3.9+).
try:
    from zoneinfo import ZoneInfo
    _KYIV_TZ = ZoneInfo("Europe/Kyiv")
except ImportError:
    # Fallback: fixed UTC+2 (winter time — safe default for most of the year)
    _KYIV_TZ = timezone(timedelta(hours=2))

# Seen users tracker for first-time user detection
_seen_users_file = "seen_users.json"
_seen_users: set = set()


def _load_seen_users() -> set:
    """Load seen user IDs from file."""
    global _seen_users
    if _seen_users:
        return _seen_users
    try:
        if os.path.exists(_seen_users_file):
            with open(_seen_users_file, "r") as f:
                data = json.load(f)
                _seen_users = set(data.get("user_ids", []))
    except (json.JSONDecodeError, OSError):
        _seen_users = set()
    return _seen_users


def _save_seen_users() -> None:
    """Save seen user IDs to file."""
    with open(_seen_users_file, "w") as f:
        json.dump({"user_ids": list(_seen_users)}, f)


def is_new_user(user_id: int) -> bool:
    """Check if user is new, and mark as seen."""
    seen = _load_seen_users()
    if user_id in seen:
        return False
    seen.add(user_id)
    _save_seen_users()
    return True


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON with Kyiv timezone."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(_KYIV_TZ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Include extra_data if present
        extra = getattr(record, "extra_data", {})
        log_data.update(extra)

        return json.dumps(log_data, ensure_ascii=False)


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


def log_new_user(user) -> None:
    """Log when a first-time user starts the bot."""
    log_data = {
        "event": "new_user_started",
        "message": "New user started bot",
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
    }
    logging.info("new_user_started", extra={"extra_data": log_data})


def log_bot_added_to_chat(chat, added_by) -> None:
    """Log when the bot is added to a chat."""
    log_data = {
        "event": "bot_added_to_chat",
        "message": "Bot added to chat",
        "chat": {
            "id": chat.id,
            "name": getattr(chat, "title", None),
            "type": getattr(chat, "type", None),
        },
        "added_by": {
            "id": added_by.id,
            "name": getattr(added_by, "first_name", None),
            "username": getattr(added_by, "username", None),
        },
    }
    logging.info("bot_added_to_chat", extra={"extra_data": log_data})


def log_bot_removed_from_chat(chat, removed_by) -> None:
    """Log when the bot is removed from a chat."""
    log_data = {
        "event": "bot_removed_from_chat",
        "message": "Bot removed from chat",
        "chat": {
            "id": chat.id,
            "name": getattr(chat, "title", None),
            "type": getattr(chat, "type", None),
        },
        "removed_by": {
            "id": removed_by.id,
            "name": getattr(removed_by, "first_name", None),
            "username": getattr(removed_by, "username", None),
        },
    }
    logging.info("bot_removed_from_chat", extra={"extra_data": log_data})


def log_bot_status_changed(chat, user, old_status, new_status) -> None:
    """Log when bot is promoted or demoted in a chat."""
    log_data = {
        "event": "bot_status_changed",
        "message": f"Bot status changed from {old_status} to {new_status}",
        "chat": {
            "id": chat.id,
            "name": getattr(chat, "title", None),
            "type": getattr(chat, "type", None),
        },
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
        "old_status": old_status,
        "new_status": new_status,
    }
    logging.info("bot_status_changed", extra={"extra_data": log_data})


def with_request_logging(handler):
    """Decorator that adds request_received/completed/failed logging to handlers."""
    @functools.wraps(handler)
    async def wrapper(update, context):
        # Skip logging for updates without message or callback_query
        if not update.message and not update.callback_query:
            return await handler(update, context)

        request_id = uuid.uuid4().hex[:8]
        context.user_data["request_id"] = request_id

        # Extract user/chat from update
        user = update.message.from_user if update.message else update.callback_query.from_user
        chat = update.message.chat if update.message else update.callback_query.message.chat
        url = getattr(update.message, 'text', '') or ''
        platform = ""  # Platform unknown at handler start

        log_request_received(
            request_id=request_id,
            url=url,
            platform=platform,
            user=user,
            chat=chat,
        )

        start_time = time.time()

        try:
            result = await handler(update, context)
            duration_ms = int((time.time() - start_time) * 1000)
            success = context.user_data.get("_request_success", True)
            # Read metadata stored by handler
            platform = context.user_data.get("_platform", platform)
            content_type = context.user_data.get("_content_type")
            file_size_mb = context.user_data.get("_file_size_mb")
            log_request_completed(
                request_id=request_id,
                url=url,
                platform=platform,
                duration_ms=duration_ms,
                success=success,
                content_type=content_type,
                file_size_mb=file_size_mb,
            )
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            # Read platform stored by handler if available
            platform = context.user_data.get("_platform", platform)
            log_request_failed(
                request_id=request_id,
                url=url,
                platform=platform,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
    return wrapper


# Track if setup_logging has been called
_initialized = False


def setup_logging() -> None:
    """Configure logging based on LOG_OUTPUT environment variable."""
    global _initialized, _seen_users_file
    if _initialized:
        return
    _initialized = True

    from config import LOG_OUTPUT, LOG_DIR, SEEN_USERS_FILE
    _seen_users_file = SEEN_USERS_FILE

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
