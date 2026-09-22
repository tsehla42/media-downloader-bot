# Admin Controls

Bot admin checks and group management.

## Bot Admin Definition

A bot admin is a user whose ID is in the `BOT_ADMIN_IDS` environment variable.

```bash
BOT_ADMIN_IDS=123456789,987654321
```

- Empty = anyone can add bot to groups
- Configured = only listed users can add bot to groups

## Group Addition Flow

When bot is added to a group:

1. `my_chat_member_handler` receives `ChatMemberUpdated`
2. Checks if `new_chat_member.status` is "member" (bot added)
3. If no `BOT_ADMIN_IDS` configured: allow (empty = anyone can add)
4. If `from_user.id` is in `BOT_ADMIN_IDS`: allow (bot admin can always add)
5. Check if at least one bot admin is already in the group via `getChatMember`
   - If no bot admin in group: reject, leave
6. If `from_user.username` is "GroupAnonymousBot" (anonymous admin): allow (bot admin presence is sufficient)
7. If `from_user` is in `ALLOWED_USER_IDS`: allow (trusted user, skip group admin check)
8. Check if `from_user` is a group admin with `can_invite_users` via `getChatMember`
   - If not admin or no invite rights: reject, leave
9. Allow — log `bot_added_to_chat` event

## Implementation

```python
# src/handlers.py (simplified)
async def my_chat_member_handler(update, context):
    # If no bot admins configured, allow anyone
    if not BOT_ADMIN_IDS:
        log_bot_added_to_chat(chat, from_user)
        return

    # Bot admin can always add
    if is_bot_admin(from_user.id):
        log_bot_added_to_chat(chat, from_user)
        return

    # Check if at least one bot admin is in the group
    if not await _any_bot_admin_in_group():
        # Reject — no bot admin present
        await context.bot.leave_chat(chat.id)
        return

    # Anonymous admin — bot admin presence is sufficient
    if from_user.username == "GroupAnonymousBot":
        log_bot_added_to_chat(chat, from_user)
        return

    # Allowed user — trusted, skip group admin check
    if _is_allowed(from_user.id):
        log_bot_added_to_chat(chat, from_user)
        return

    # Must be group admin with invite rights
    adder_member = await context.bot.getChatMember(chat.id, from_user.id)
    if adder_member.status != "administrator" or not adder_member.can_invite_users:
        await context.bot.leave_chat(chat.id)
        return

    log_bot_added_to_chat(chat, from_user)
```

## Events

### bot_added_to_chat
Bot successfully added to a group by an admin.

```json
{
  "event": "bot_added_to_chat",
  "chat_id": -1003804964305,
  "chat_name": "Test Group",
  "added_by": {"id": 12345678, "name": "Alice"}
}
```

### bot_rejected_group_addition
Bot rejected group addition by non-admin.

```json
{
  "event": "bot_rejected_group_addition",
  "chat_id": -1003804964305,
  "chat_name": "Test Group",
  "added_by": {"id": 123456789, "name": "Unauthorized User"}
}
```

### bot_removed_from_chat
Bot removed from a group.

```json
{
  "event": "bot_removed_from_chat",
  "chat_id": -1003804964305,
  "chat_name": "Test Group",
  "removed_by": {"id": 12345678, "name": "Alice"}
}
```

## Related

- [Service Logging](../logs/service.md) - Where these events are logged
- [Authorization](../p2p-chats/authorization.md) - User authorization checks
