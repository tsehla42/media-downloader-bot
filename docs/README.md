# Media Downloader Bot

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram.

## Overview

Users paste a URL, get the media back. Also silently attempts gallery-dl for 100+ other services.

## Documentation

- [Group Chats](group-chats/) - How bot works in groups
- [Guest Mode](guest-mode/) - Bot API 10.0 guest mode
- [P2P Chats](p2p-chats/) - Private chat behavior
- [Logging](logs/) - Logging system
- [Content Delivery](content-delivery/) - Media downloading

## Quick Start

1. Clone repo
2. Copy `.env.example` to `.env`
3. Add `BOT_TOKEN` to `.env`
4. Run `docker compose up -d --build`

## Architecture

Modular design. Each module has one clear responsibility.

### Modules
- `config.py` - Settings from .env
- `auth.py` - Authorization checks
- `commands.py` - User commands
- `handlers.py` - Telegram handlers
- `guest.py` - Guest mode
- `downloader.py` - yt-dlp/gallery-dl subprocess
- `platforms/` - Platform-specific logic

### Data Flow
1. User sends URL
2. Bot detects platform
3. Bot downloads media
4. Bot sends to user
5. Bot cleans up

## Development

```bash
docker compose up -d --build
docker logs -f media-downloader-bot
```

## Deployment

See [Deploy Guide](deploy.md) (gitignored)