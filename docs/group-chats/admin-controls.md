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
   - Accepts status `"administrator"`, `"member"`, or `"creator"` (group owner)
   - Each lookup result (status or error) is logged as a `bot_admin_lookup` event
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

## Known Gotchas

### Anonymous Bot Admin Fails the Presence Check

**Symptom:** Bot replies "Not everyone can add me to groups" and leaves immediately, even though a user from `BOT_ADMIN_IDS` is already an admin of the group.

**Cause:** The "is a bot admin present" check (step 5) calls `getChatMember(chat.id, admin_id)` for each bot admin. Per the official Bot API, `getChatMember` for *other users* is only guaranteed to work when the **bot itself** is an administrator — and at this moment the bot has just been added as a regular member. A bot admin who is acting as an **anonymous admin** (Group Info → Administrators → "Stay Anonymous") can fail to resolve in this check, so the check returns no bot admin and the bot rejects the addition.

This is observable in the logs: `bot_rejected_group_addition` with `added_by.username == "GroupAnonymousBot"`, followed immediately by `bot_removed_from_chat`. Each presence-check lookup is logged to `service.jsonl` as a `bot_admin_lookup` event with the resolved status or the error message, so a failed lookup shows up there instead of disappearing.

**Workaround:** Before adding the bot, turn off anonymous mode for the bot admin in the group (or ensure a non-anonymous bot admin is present). Alternatively, have a bot admin add the bot non-anonymously — that path (`is_bot_admin(from_user.id)`) skips the presence check entirely.

**Verified:** A group addition was rejected at 17:16 with a bot admin present as anonymous admin; after disabling anonymous mode for that admin, the identical addition succeeded.

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
