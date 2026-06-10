# Guest Mode

Bot API 10.0 guest mode allows users to mention @botname in any chat to download media.

## Overview

When a user mentions the bot with `@username` in any chat (groups, P2P, or chats the bot isn't in), the bot receives a `guest_message` update and can reply using `answerGuestQuery()`.

## Key Concepts

- Users mention bot with `@username` in any chat
- Bot receives `guest_message` update (separate from `message`)
- Bot replies using `answerGuestQuery()` method (not `sendMessage`)
- Bot only sees the specific message it was tagged in + replies to that message
- Bot CANNOT see chat member list or other messages
- Up to 3 guest bots can be mentioned per message

## Setup

1. Enable via BotFather → MiniApp → enable "Guest Mode"
2. Set `GUEST_MODE_ENABLED=true` in .env
3. Set `STORAGE_CHANNEL_ID` to a private channel (bot must be admin)

## Documentation

- [Implementation Details](implementation.md) - Technical implementation and API details
- [Troubleshooting](troubleshooting.md) - Common issues and debugging tips

## Related

- [Guest API in Group Chats](../group-chats/guest-api.md)
- [Logging Guest Requests](../logs/requests.md)
