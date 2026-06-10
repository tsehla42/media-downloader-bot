# User Commands

User-facing commands in P2P chats.

## /start

Welcome message when user starts the bot.

**Response:**

```
Media Downloader Bot

Send me a YouTube, TikTok, or Instagram URL and I'll download it for you
You can send multiple URLs in one message or send them one by one.
Max file size: 50MB

Commands:
/help - Show supported platforms and commands
/audio <url> - Download as audio (MP3)
/caption on|off - Toggle video captions
```

**Implementation:** `src/commands.py:start_command()`

## /help

Shows supported platforms and commands.

**Response:**

```
Supported platforms:
- YouTube (videos, shorts)
- TikTok (videos, no watermark)
- Instagram (reels, posts, carousels)

Commands:
/audio <url> - Download as audio (MP3)
/caption on - Show video captions
/caption off - Remove video captions (default)

Max file size: 50MB
You can send multiple URLs in one message.
```

**Implementation:** `src/commands.py:help_command()`

## /audio

Download audio only (MP3) from a YouTube or YouTube Music URL.

**Usage:**

```
/audio https://www.youtube.com/watch?v=...
```

**Response:** Sends an audio file with the track title.

**Implementation:** `src/handlers.py:audio_command()`

## /caption

Toggle video captions on/off.

**Usage:**

```
/caption on    # Enable captions
/caption off   # Disable captions (default)
/caption       # Show current setting
```

**Behavior:**

- `/caption on` or `/caption 1` or `/caption true` or `/caption yes` -> Enable captions (videos include title)
- `/caption off` or `/caption 0` or `/caption false` or `/caption no` -> Disable captions (default, videos sent without description)
- `/caption` (no argument) -> Show current setting and usage info
- Per-user preference, stored in memory (resets on bot restart)

**Responses:**

```
Captions enabled. Videos will include the title
```

```
Captions removed. Videos will be sent without description
```

```
Current caption setting: OFF (no captions)

Usage:
/caption on - Show video captions
/caption off - Remove video captions (default)
```

**Implementation:** `src/commands.py:caption_command()`

### How Captions Work

The `get_caption_for_user()` function in `src/commands.py` controls caption behavior:

- Default: captions OFF (user preference stored as `True` meaning "remove caption")
- When captions are ON: video messages include a caption with the video title (truncated to 1024 characters)
- When captions are OFF: videos are sent without captions

**Note:** The default is captions OFF. Users must run `/caption on` to enable them.

## Authorization

All commands check authorization before responding. Unauthorized users get one "not authorized" message on first attempt, then are silently ignored. See [Authorization](authorization.md).

## Related

- [Authorization](authorization.md) - User authorization checks
- [P2P Chats](README.md) - Private chat behavior overview
