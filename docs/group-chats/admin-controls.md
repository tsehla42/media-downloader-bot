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
3. Checks if `from_user.id` is in `BOT_ADMIN_IDS`
4. If admin: log `bot_added_to_chat` event, allow
5. If not admin: log `bot_rejected_group_addition` event, reject, leave group

## Implementation

```python
# src/handlers.py
async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle bot added/removed from chats."""
    chat_member = update.my_chat_member
    if chat_member.new_chat_member.status == "member":
        # Bot was added to a group
        from_user = chat_member.from_user
        if not is_bot_admin(from_user.id):
            # Reject - not admin
            service_logger.warning("Bot rejected group addition", extra={
                "event": "bot_rejected_group_addition",
                "chat_id": chat_member.chat.id,
                "added_by": {"id": from_user.id, "name": from_user.full_name}
            })
            await context.bot.leave_chat(chat_member.chat.id)
            return
        # Admin - allow
        service_logger.info("Bot added to group", extra={
            "event": "bot_added_to_chat",
            "chat_id": chat_member.chat.id,
            "added_by": {"id": from_user.id, "name": from_user.full_name}
        })
```

## Events

### bot_added_to_chat
Bot successfully added to a group by an admin.

```json
{
  "event": "bot_added_to_chat",
  "chat_id": -1003804964305,
  "chat_name": "mememedia test",
  "added_by": {"id": 628055047, "name": "Меменасе"}
}
```

### bot_rejected_group_addition
Bot rejected group addition by non-admin.

```json
{
  "event": "bot_rejected_group_addition",
  "chat_id": -1003804964305,
  "chat_name": "mememedia test",
  "added_by": {"id": 123456789, "name": "Unauthorized User"}
}
```

### bot_removed_from_chat
Bot removed from a group.

```json
{
  "event": "bot_removed_from_chat",
  "chat_id": -1003804964305,
  "chat_name": "mememedia test",
  "removed_by": {"id": 628055047, "name": "Меменасе"}
}
```

## Related

- [Service Logging](../logs/service.md) - Where these events are logged
- [Authorization](../p2p-chats/authorization.md) - User authorization checks
