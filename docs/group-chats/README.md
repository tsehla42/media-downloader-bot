# Group Chats

How the bot behaves in group chats that it's added to.

## Overview

The bot can be added to Telegram groups and supergroups to download media for all members.

## Key Concepts

- Bot must be added by a bot admin (if `BOT_ADMIN_IDS` is configured)
- Bot can be disabled in groups via `ALLOWED_GROUP_IDS`
- Guest mode allows users to mention bot without it being a member
- Bot only receives messages that mention it or replies to its messages (unless privacy mode is disabled)

## Security

### Bot Admin Checks
- When bot is added to a group, `my_chat_member_handler` checks if the user who added it is a bot admin
- If not admin, bot rejects the addition and leaves
- See [Admin Controls](admin-controls.md) for details

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
