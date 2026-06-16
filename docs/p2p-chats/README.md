# P2P Chats

How the bot behaves in private (1-on-1) chats with users.

## Overview

Users can interact with the bot directly in private chats to download media by sending URLs or using commands.

## Key Concepts

- Users must be authorized (in allowlist) to use the bot
- Unauthorized users get one "not authorized" message, then are silently ignored
- Bot responds to URL messages and `/audio` commands
- Authorization can be configured to require an allowlist or allow all users
- Caption preferences are per-user and stored in memory (reset on restart)

## Authorization

- Users must be in `ALLOWED_USER_IDS` (merged from `allowed-users.json` + env var)
- Empty sources = allow all users
- Configured sources = user must be in list
- See [Authorization](authorization.md) for details

## Commands

- `/start` - Welcome message
- `/help` - Supported platforms and commands
- `/audio <url>` - Download as audio (MP3)
- `/caption on|off` - Toggle video captions
- See [Commands](commands.md) for details

## Message Handling

### URL Messages
- Detect platform (YouTube, TikTok, Instagram, or gallery-dl fallback)
- Download media
- Send to user

### /audio Commands
- Download audio only (YouTube, YouTube Music)
- Send as audio file

### Replies to Bot Messages
- Retry download of the original URL

## Documentation

- [Authorization](authorization.md) - User allowlists, unauthorized handling
- [Commands](commands.md) - User commands (/start, /help, /audio, /caption)

## Related

- [Group Chats](../group-chats/) - Group chat behavior
- [Guest Mode](../guest-mode/) - Bot API 10.0 guest mode
