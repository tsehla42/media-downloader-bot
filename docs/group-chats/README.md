# Group Chats

How the bot behaves in group chats that it's added to.

## Overview

The bot can be added to Telegram groups and supergroups to download media for all members.

## Key Concepts

- Bot can be added by: bot admins, group admins with invite rights (if a bot admin is in the group), anonymous admins (if a bot admin is in the group), or allowed users (`ALLOWED_USER_IDS`)
- Bot can be disabled in groups via `ALLOWED_GROUP_IDS`
- Guest mode allows users to mention bot without it being a member
- Bot only receives messages that mention it or replies to its messages (unless privacy mode is disabled)

## Security

### Bot Admin Checks
- When bot is added to a group, `my_chat_member_handler` checks multiple conditions
- Bot admin can always add; anonymous admin and allowed users can add if a bot admin is in the group; group admins with invite rights can add if a bot admin is in the group
- **Gotcha:** a bot admin who is an *anonymous admin* may not be resolvable by the `getChatMember` presence check — the bot then wrongly rejects the addition and leaves. Turn off anonymous mode for that admin before adding the bot. See [Admin Controls](admin-controls.md#known-gotchas)
- See [Admin Controls](admin-controls.md) for the full flow

### Group Allowlists
- `ALLOWED_GROUP_IDS` env var restricts which groups the bot can be in
- Empty = allow all groups
- Configured = only listed groups allowed

## Behavior

### Privacy Mode
- **Enabled (default):** Bot only receives messages that mention it or replies to its messages
- **Disabled:** Bot receives all messages in the group
- Disable via BotFather: `/setprivacy` → Disable

### Message Handling
- URL messages → Download media
- `/audio` commands → Download audio only
- Replies to bot messages → Retry download
- Messages mentioning bot → Guest mode (if enabled)

## Documentation

- [Admin Controls](admin-controls.md) - Bot admin checks, group additions/removals
- [Guest API](guest-api.md) - Guest API reference for group context

## Related

- [Guest Mode](../guest-mode/) - Bot API 10.0 guest mode
- [P2P Chats](../p2p-chats/) - Private chat behavior
