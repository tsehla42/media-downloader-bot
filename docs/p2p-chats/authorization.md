# Authorization

User authorization and access control in private chats.

## Overview

The bot uses an allowlist system to control which users can access it in P2P chats. Groups are always allowed (the bot only exists if an admin added it).

## Configuration

### Environment Variables

```bash
# Comma-separated user IDs
ALLOWED_USER_IDS=123456789,987654321

# Bot admins (can add bot to groups)
BOT_ADMIN_IDS=123456789
```

### File-based Allowlist

`allowed-users.json` - Array of objects with `id` field:

```json
[
  {"id": 123456789, "name": "User 1"},
  {"id": 987654321, "name": "User 2"}
]
```

Also supports legacy format (dict with `allowed_user_ids` array).

## Priority

1. `allowed-users.json` (file-based)
2. `ALLOWED_USER_IDS` (env var)

Both are merged into a single allowlist at startup.

## Behavior

### Sources Configured
- If user is in allowlist -> authorized
- If user is not in allowlist -> unauthorized

### No Sources Configured
- All users are authorized
- Empty `ALLOWED_USER_IDS` and no `allowed-users.json` = allow all

## Unauthorized User Handling

### First Attempt
- Bot sends: "You are not authorized to use this bot"
- Logs `unauthorized_access` event to `service.jsonl`
- User marked as notified (in-memory set, resets on restart)

### Subsequent Attempts
- Bot silently ignores (no response, no logging)

### Guest Mode
- Separate notification tracking via `was_notified_guest()` / `mark_notified_guest()`
- Auth check only runs when URL is present (user trying to download)
- Without URL: unauthorized users silently ignored (no message, no logging)
- With URL: first attempt gets "You are not authorized", subsequent ignored

## Implementation

```python
# src/auth.py
def is_authorized(update: Update) -> bool:
    """Check if request is authorized."""
    if is_group_chat(update):
        return True  # Groups always allowed
    if update.message and update.message.from_user:
        return _is_allowed(update.message.from_user.id)
    return False

def _is_allowed(user_id: int) -> bool:
    """Check if user is in allowlist.
    No sources configured = allow all.
    Sources configured but user not in list = deny.
    """
    if not ALLOWED_IDS_CONFIGURED:
        return True
    return user_id in ALLOWED_USER_IDS
```

## Events

### unauthorized_access

Logged to `service.jsonl`:

```json
{
  "event": "unauthorized_access",
  "user_id": 123456789,
  "user_name": "Unauthorized User",
  "command": "/start"
}
```

## Related

- [Admin Controls](../group-chats/admin-controls.md) - Bot admin checks
- [Service Logging](../logs/service.md) - Where these events are logged
