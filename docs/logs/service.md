# Service Logging

The `service.jsonl` file contains bot events and service logs.

## Purpose

Captures bot lifecycle events:
- Bot start/stop
- Chat membership changes (added/removed from groups)
- New user events
- Authorization events

## Events

### Bot Started
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "Bot started",
  "event": "bot_started",
  "mode": "production"
}
```

### Bot Added to Group
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "Bot added to group",
  "event": "bot_added_to_chat",
  "chat_id": -1003804964305,
  "chat_name": "Test Group",
  "added_by": {"id": 12345678, "name": "Alice"}
}
```

### Bot Removed from Group
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "Bot removed from group",
  "event": "bot_removed_from_chat",
  "chat_id": -1003804964305,
  "chat_name": "Test Group",
  "removed_by": {"id": 12345678, "name": "Alice"}
}
```

### Bot Rejected Group Addition
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "WARNING",
  "message": "Bot rejected group addition (non-admin)",
  "event": "bot_rejected_group_addition",
  "chat_id": -1003804964305,
  "chat_name": "Test Group",
  "added_by": {"id": 123456789, "name": "Unauthorized User"}
}
```

### New User
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "New user started bot",
  "event": "new_user",
  "user_id": 12345678,
  "user_name": "Alice",
  "username": "user_alice"
}
```

### Unauthorized Access
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "WARNING",
  "message": "Unauthorized access attempt",
  "event": "unauthorized_access",
  "user_id": 123456789,
  "user_name": "Unauthorized User"
}
```

## Logger

Service events are logged via `service_logger` in `src/logging_config.py`:

```python
from src.logging_config import service_logger

service_logger.info("Bot added to group", extra={
    "event": "bot_added_to_chat",
    "chat_id": chat_id,
    "chat_name": chat_name,
    "added_by": {"id": user_id, "name": user_name}
})
```

## Related

- [Request Lifecycle](requests.md) - User request events
- [Details Logging](details.md) - Download steps
