import contextvars
import functools
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from logging.handlers import RotatingFileHandler

# Context variable for request_id — allows downloader/platform code to log
# with request_id without passing Telegram context through the call stack.
_current_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_request_id", default=None
)


def set_current_request_id(request_id: str) -> None:
    """Set the current request_id in context (called by handlers before downloads)."""
    _current_request_id.set(request_id)


def get_current_request_id() -> str | None:
    """Get the current request_id (used by downloader/platform log calls)."""
    return _current_request_id.get()

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

class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON with Kyiv timezone."""

    # Standard LogRecord attributes to skip when collecting extras
    _RECORD_ATTRS = frozenset({
        "name", "msg", "args", "created", "relativeCreated", "exc_info",
        "exc_text", "stack_info", "lineno", "funcName", "pathname", "filename",
        "module", "levelname", "levelno", "msecs", "thread", "threadName",
        "processName", "process", "message", "taskName", "extra_data",
    })

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(_KYIV_TZ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Include exception traceback if present
        if record.exc_info and record.exc_info[1]:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include extra_data if present (used by request lifecycle functions)
        extra = getattr(record, "extra_data", {})
        log_data.update(extra)

        # Include any individual extra fields set via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in self._RECORD_ATTRS and key not in log_data and not key.startswith("_"):
                log_data[key] = value

        return json.dumps(log_data, ensure_ascii=False)


class RequestsFilter(logging.Filter):
    """Filter that only accepts records from media_downloader.requests logger."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("media_downloader.requests")


class DetailsFilter(logging.Filter):
    """Filter that only accepts records from media_downloader.details logger."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("media_downloader.details")


class ServiceFilter(logging.Filter):
    """Filter that only accepts records from media_downloader.service logger."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("media_downloader.service")


class ErrorsFilter(logging.Filter):
    """Filter that only accepts records from media_downloader.errors logger."""
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name.startswith("media_downloader.errors")


requests_logger = logging.getLogger("media_downloader.requests")
details_logger = logging.getLogger("media_downloader.details")
service_logger = logging.getLogger("media_downloader.service")
error_logger = logging.getLogger("media_downloader.errors")


def _build_forwarded_dict(message: object) -> dict | None:
    """Build forwarded info dict from message.forward_origin, or None if not forwarded."""
    origin = getattr(message, "forward_origin", None)
    if origin is None:
        return None

    origin_type = getattr(origin, "type", None)
    date = getattr(origin, "date", None)
    date_str = date.isoformat() if date else None

    if origin_type == "user":
        sender = getattr(origin, "sender_user", None)
        if sender:
            return {
                "id": sender.id,
                "name": getattr(sender, "first_name", None),
                "username": getattr(sender, "username", None),
                "date": date_str,
            }
    elif origin_type == "hidden_user":
        return {
            "name": getattr(origin, "sender_user_name", None),
            "date": date_str,
        }
    elif origin_type == "channel":
        chat = getattr(origin, "chat", None)
        return {
            "chat_id": getattr(chat, "id", None) if chat else None,
            "name": getattr(chat, "title", None) if chat else None,
            "username": getattr(chat, "username", None) if chat else None,
            "author_signature": getattr(origin, "author_signature", None),
            "date": date_str,
        }
    elif origin_type == "chat":
        sender_chat = getattr(origin, "sender_chat", None)
        return {
            "chat_id": getattr(sender_chat, "id", None) if sender_chat else None,
            "name": getattr(sender_chat, "title", None) if sender_chat else None,
            "username": getattr(sender_chat, "username", None) if sender_chat else None,
            "author_signature": getattr(origin, "author_signature", None),
            "date": date_str,
        }

    return None


def _enrich_chat(
    chat: object,
    user: object = None,
    chat_owner_name: str | None = None,
    chat_owner_username: str | None = None,
) -> dict:
    """Build enriched chat dict with name and username.

    For private chats, combines caller and chat owner as "caller | owner".
    For all types, adds username only when non-null/non-empty.
    """
    chat_dict = {"id": chat.id, "type": getattr(chat, "type", None)}
    is_private = getattr(chat, "type", None) == "private"

    name = getattr(chat, "title", None)
    username = getattr(chat, "username", None)

    if is_private:
        caller_name = getattr(user, "first_name", None) if user else None
        caller_username = getattr(user, "username", None) if user else None
        if not name and chat_owner_name:
            name = f"{caller_name} | {chat_owner_name}" if caller_name else chat_owner_name
        elif not name and caller_name:
            name = caller_name
        if not username and chat_owner_username:
            username = f"{caller_username} | {chat_owner_username}" if caller_username else chat_owner_username
        elif not username and caller_username:
            username = caller_username

    if name:
        chat_dict["name"] = name
    if username:
        chat_dict["username"] = username
    return chat_dict


def log_request_received(
    request_id: str,
    url: str,
    user: object,
    chat: object,
    event: str = "request_received",
    forwarded: dict | None = None,
) -> None:
    """Log when a request is received."""
    messages = {
        "request_received": "Request received",
        "reply_to_retry_received": "Reply to retry received",
    }
    message = messages.get(event, "Request received")
    log_data = {
        "event": event,
        "message": message,
        "request_id": request_id,
        "url": url,
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
        "chat": _enrich_chat(chat, user),
    }
    if forwarded:
        log_data["forwarded"] = forwarded
    requests_logger.info(event, extra={"extra_data": log_data})


def log_request_completed(
    request_id: str,
    url: str,
    platform: str,
    duration_ms: int,
    success: bool,
    content_type: str | None = None,
    file_size_mb: float | None = None,
    error: str | None = None,
    user: object = None,
    chat: object = None,
    event: str = "request_completed",
    forwarded: dict | None = None,
    skip_reason: str | None = None,
) -> None:
    """Log when a request completes (success or expected failure)."""
    messages = {
        "request_completed": "Request completed",
        "reply_to_retry_completed": "Reply to retry completed",
    }
    message = messages.get(event, "Request completed")
    log_data = {
        "event": event,
        "success": success,
        "message": message,
        "request_id": request_id,
        "url": url,
        "platform": platform,
        "duration_ms": duration_ms,
        "content_type": content_type,
        "file_size_mb": file_size_mb,
    }
    if error:
        log_data["error"] = error
    if skip_reason:
        log_data["skip_reason"] = skip_reason
    if user:
        log_data["user"] = {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        }
    if chat:
        log_data["chat"] = _enrich_chat(chat, user)
    if forwarded:
        log_data["forwarded"] = forwarded
    requests_logger.info("request_completed", extra={"extra_data": log_data})


def log_request_failed(
    request_id: str,
    url: str,
    platform: str,
    error: str,
    error_type: str,
    user: object = None,
    chat: object = None,
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
    if user:
        log_data["user"] = {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        }
    if chat:
        log_data["chat"] = _enrich_chat(chat, user)
    requests_logger.error("request_failed", extra={"extra_data": log_data})


def log_guest_request_received(
    request_id: str,
    guest_query_id: str,
    url: str,
    caller: object,
    chat: object,
    reply: dict | None = None,
    chat_owner_name: str | None = None,
    chat_owner_username: str | None = None,
    forwarded: dict | None = None,
) -> None:
    """Log when a guest request is received (only when URL is present)."""
    log_data = {
        "event": "guest_request_received",
        "message": "Guest request received",
        "request_id": request_id,
        "guest_query_id": guest_query_id,
        "url": url,
        "user": {
            "id": caller.id,
            "name": getattr(caller, "first_name", None),
            "username": getattr(caller, "username", None),
        },
        "chat": _enrich_chat(chat, caller, chat_owner_name, chat_owner_username),
    }
    if reply is not None:
        log_data["reply"] = reply
    if forwarded:
        log_data["forwarded"] = forwarded
    requests_logger.info("guest_request_received", extra={"extra_data": log_data})


def log_guest_request_completed(
    request_id: str,
    guest_query_id: str,
    url: str,
    platform: str | None,
    duration_ms: int,
    success: bool,
    content_type: str | None = None,
    file_size_mb: float | None = None,
    error: str | None = None,
    cache_hit: bool = False,
    caller: object = None,
    chat: object = None,
    chat_owner_name: str | None = None,
    chat_owner_username: str | None = None,
    forwarded: dict | None = None,
) -> None:
    """Log when a guest request completes."""
    log_data = {
        "event": "guest_request_completed",
        "success": success,
        "message": "Guest request completed",
        "request_id": request_id,
        "guest_query_id": guest_query_id,
        "url": url,
        "platform": platform,
        "duration_ms": duration_ms,
        "cache": cache_hit,
        "content_type": content_type,
        "file_size_mb": file_size_mb,
    }
    if error:
        log_data["error"] = error
    if caller:
        log_data["user"] = {
            "id": caller.id,
            "name": getattr(caller, "first_name", None),
            "username": getattr(caller, "username", None),
        }
    if chat:
        log_data["chat"] = _enrich_chat(chat, caller, chat_owner_name, chat_owner_username)
    if forwarded:
        log_data["forwarded"] = forwarded
    requests_logger.info("guest_request_completed", extra={"extra_data": log_data})


def log_bot_added_to_chat(chat, added_by) -> None:
    """Log when the bot is added to a chat."""
    log_data = {
        "event": "bot_added_to_chat",
        "message": "Bot added to chat",
        "chat": _enrich_chat(chat),
        "added_by": {
            "id": added_by.id,
            "name": getattr(added_by, "first_name", None),
            "username": getattr(added_by, "username", None),
        },
    }
    service_logger.info("bot_added_to_chat", extra={"extra_data": log_data})


def log_bot_rejected_group_addition(chat, added_by) -> None:
    """Log when a non-admin tries to add the bot to a group and is rejected."""
    log_data = {
        "event": "bot_rejected_group_addition",
        "message": "Bot rejected group addition (non-admin)",
        "chat": _enrich_chat(chat),
        "added_by": {
            "id": added_by.id,
            "name": getattr(added_by, "first_name", None),
            "username": getattr(added_by, "username", None),
        },
    }
    service_logger.info("bot_rejected_group_addition", extra={"extra_data": log_data})


def log_unauthorized_access(user, chat, command: str = "") -> None:
    """Log when an unauthorized user tries to access the bot."""
    log_data = {
        "event": "unauthorized_access",
        "message": "Unauthorized user tried to access the bot",
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
        "chat": _enrich_chat(chat, user),
    }
    if command:
        log_data["command"] = command
    service_logger.info("unauthorized_access", extra={"extra_data": log_data})


def log_bot_removed_from_chat(chat, removed_by) -> None:
    """Log when the bot is removed from a chat."""
    log_data = {
        "event": "bot_removed_from_chat",
        "message": "Bot removed from chat",
        "chat": _enrich_chat(chat),
        "removed_by": {
            "id": removed_by.id,
            "name": getattr(removed_by, "first_name", None),
            "username": getattr(removed_by, "username", None),
        },
    }
    service_logger.info("bot_removed_from_chat", extra={"extra_data": log_data})


def log_bot_status_changed(chat, user, old_status, new_status) -> None:
    """Log when bot is promoted or demoted in a chat."""
    log_data = {
        "event": "bot_status_changed",
        "message": f"Bot status changed from {old_status} to {new_status}",
        "chat": _enrich_chat(chat),
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
        "old_status": old_status,
        "new_status": new_status,
    }
    service_logger.info("bot_status_changed", extra={"extra_data": log_data})


def _extract_admin_rights(member) -> dict | None:
    """Extract admin rights from a ChatMemberAdministrator, or None if not admin.

    Only includes fields with concrete values (bool, str, int, None).
    Skips auto-created proxy objects (e.g. MagicMock) that have no real value.
    """
    if not hasattr(member, "status") or member.status != "administrator":
        return None

    _FIELDS = (
        "can_manage_chat", "can_delete_messages", "can_manage_video_chats",
        "can_restrict_members", "can_promote_members", "can_change_info",
        "can_invite_users", "can_post_messages", "can_edit_messages",
        "can_pin_messages", "can_manage_topics", "custom_title",
    )
    rights = {}
    for field in _FIELDS:
        val = getattr(member, field, None)
        # Only include concrete values (bool, str, int, None)
        if val is None or isinstance(val, (bool, str, int)):
            rights[field] = val
    return rights


def log_admin_rights_changed(chat, user, old_rights, new_rights, event) -> None:
    """Log admin rights changes (added as admin, rights changed).

    Args:
        chat: The chat object.
        user: The user who made the change.
        old_rights: Previous admin rights dict (None if bot was not admin before).
        new_rights: New admin rights dict.
        event: One of "bot_added_as_admin", "bot_admin_rights_changed".
    """
    # Compute delta — only include fields that actually changed
    added = {}
    removed = {}
    all_keys = set((old_rights or {}).keys()) | set((new_rights or {}).keys())
    for key in all_keys:
        old_val = (old_rights or {}).get(key)
        new_val = (new_rights or {}).get(key)
        if old_val != new_val:
            if new_val and not old_val:
                added[key] = new_val
            elif old_val and not new_val:
                removed[key] = old_val
            else:
                added[key] = new_val
                removed[key] = old_val

    log_data = {
        "event": event,
        "message": event.replace("_", " "),
        "chat": _enrich_chat(chat),
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
    }
    if new_rights:
        log_data["new_admin_rights"] = new_rights
    if added:
        log_data["rights_added"] = added
    if removed:
        log_data["rights_removed"] = removed

    service_logger.info(event, extra={"extra_data": log_data})


def log_custom_title_changed(chat, user, old_title, new_title) -> None:
    """Log when bot's admin custom title changes."""
    log_data = {
        "event": "bot_custom_title_changed",
        "message": "Bot custom title changed",
        "chat": _enrich_chat(chat),
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
        "old_custom_title": old_title,
        "new_custom_title": new_title,
    }
    service_logger.info("bot_custom_title_changed", extra={"extra_data": log_data})


def log_user_blocked_bot(chat, user) -> None:
    """Log when a user blocks the bot in a private chat."""
    log_data = {
        "event": "user_blocked_bot",
        "message": "User blocked bot",
        "chat": _enrich_chat(chat, user),
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
    }
    service_logger.info("user_blocked_bot", extra={"extra_data": log_data})


def log_user_unblocked_bot(chat, user) -> None:
    """Log when a user unblocks the bot in a private chat."""
    log_data = {
        "event": "user_unblocked_bot",
        "message": "User unblocked bot",
        "chat": _enrich_chat(chat, user),
        "user": {
            "id": user.id,
            "name": getattr(user, "first_name", None),
            "username": getattr(user, "username", None),
        },
    }
    service_logger.info("user_unblocked_bot", extra={"extra_data": log_data})


def with_request_logging(handler):
    """Decorator that adds request_received/completed/failed logging to handlers."""
    @functools.wraps(handler)
    async def wrapper(update, context):
        from utils import is_valid_url, extract_urls

        # Skip logging for updates without message or callback_query
        if not update.message and not update.callback_query:
            return await handler(update, context)

        # Only log if the message actually contains a valid URL
        text = getattr(update.message, 'text', '') if update.message else ''
        if text:
            urls = extract_urls(text)
            if not urls or not is_valid_url(text):
                return await handler(update, context)

        request_id = uuid.uuid4().hex[:8]
        context.user_data["request_id"] = request_id
        set_current_request_id(request_id)

        # Extract user/chat from update
        user = update.message.from_user if update.message else update.callback_query.from_user
        chat = update.message.chat if update.message else update.callback_query.message.chat
        forwarded = _build_forwarded_dict(update.message) if update.message else None
        url = text  # Already validated above
        platform = ""  # Platform unknown at handler start

        log_request_received(
            request_id=request_id,
            url=url,
            user=user,
            chat=chat,
            forwarded=forwarded,
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
            skip_reason = context.user_data.get("_skip_reason")
            log_request_completed(
                request_id=request_id,
                url=url,
                platform=platform,
                duration_ms=duration_ms,
                success=success,
                content_type=content_type,
                file_size_mb=file_size_mb,
                user=user,
                chat=chat,
                forwarded=forwarded,
                skip_reason=skip_reason,
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
                user=user,
                chat=chat,
            )
            raise
    return wrapper


# Track if setup_logging has been called
_initialized = False


def _resolve_log_file(mode: str) -> str:
    """Map MODE to request log filename."""
    mode = mode.lower().strip()
    if mode in ("dev", "development"):
        return "requests.dev.jsonl"
    return "requests.jsonl"


def _resolve_detail_log_file(mode: str) -> str:
    """Map MODE to detail log filename."""
    mode = mode.lower().strip()
    if mode in ("dev", "development"):
        return "request-details.dev.jsonl"
    return "request-details.jsonl"


def _resolve_service_log_file(mode: str) -> str:
    """Map MODE to service log filename."""
    mode = mode.lower().strip()
    if mode in ("dev", "development"):
        return "service.dev.jsonl"
    return "service.jsonl"


def _resolve_error_log_file(mode: str) -> str:
    """Map MODE to error log filename."""
    mode = mode.lower().strip()
    if mode in ("dev", "development"):
        return "errors.dev.jsonl"
    return "errors.jsonl"


def log_error(
    error: Exception,
    update: object = None,
    request_id: str | None = None,
) -> None:
    """Log an unhandled error to errors.jsonl with structured metadata."""
    if request_id is None:
        request_id = get_current_request_id()

    import traceback as tb
    log_data = {
        "event": "unhandled_exception",
        "error_id": uuid.uuid4().hex[:8],
        "error_type": type(error).__name__,
        "error_message": str(error),
        "traceback": "".join(tb.format_exception(type(error), error, error.__traceback__)),
    }
    if request_id:
        log_data["request_id"] = request_id
    if update:
        if hasattr(update, "effective_chat") and update.effective_chat:
            log_data["chat_id"] = update.effective_chat.id
        if hasattr(update, "effective_user") and update.effective_user:
            log_data["user_id"] = update.effective_user.id

    error_logger.error("unhandled_exception", extra={"extra_data": log_data})


def setup_logging() -> None:
    """Configure logging based on MODE and LOG_OUTPUT environment variables.

    Creates four file handlers:
    - requests.jsonl: request lifecycle events (via requests_logger)
    - request-details.jsonl: intermediate/download steps (via details_logger)
    - service.jsonl: bot start/stop, chat membership, new user events (via service_logger)
    - errors.jsonl: unhandled exceptions with structured metadata (via error_logger)

    MODE=development|dev  → logs to *.dev.jsonl files
    MODE=production|prod  → logs to production files

    LOG_OUTPUT=console|stdout → console only
    LOG_OUTPUT=file           → file only
    LOG_OUTPUT=both           → console + file (default)
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    from config import MODE, LOG_OUTPUT, LOG_DIR, LOG_LEVEL

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    formatter = JSONFormatter()

    # Normalize LOG_OUTPUT aliases
    output = LOG_OUTPUT.lower().strip()
    if output == "stdout":
        output = "console"

    log_file = _resolve_log_file(MODE)
    detail_log_file = _resolve_detail_log_file(MODE)
    service_log_file = _resolve_service_log_file(MODE)
    error_log_file = _resolve_error_log_file(MODE)
    want_console = output in ("console", "both")
    want_file = output in ("file", "both")

    if want_file:
        os.makedirs(LOG_DIR, exist_ok=True)

        # Requests file handler — only accepts requests logger
        requests_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        requests_handler.setFormatter(formatter)
        requests_handler.addFilter(RequestsFilter())
        root.addHandler(requests_handler)

        # Details file handler — only accepts details logger
        details_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, detail_log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        details_handler.setFormatter(formatter)
        details_handler.addFilter(DetailsFilter())
        root.addHandler(details_handler)

        # Service file handler — only accepts service logger
        service_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, service_log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        service_handler.setFormatter(formatter)
        service_handler.addFilter(ServiceFilter())
        root.addHandler(service_handler)

        # Error file handler — only accepts error logger
        error_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, error_log_file),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        error_handler.setFormatter(formatter)
        error_handler.addFilter(ErrorsFilter())
        root.addHandler(error_handler)

    if want_console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)
