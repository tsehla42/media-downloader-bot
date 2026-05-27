# Media Downloader Bot - Documentation

## What Is This

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram. Users send a URL, get the media back. Supports inline queries for use in any chat.

## Why It Exists

Sharing media from these platforms in Telegram is annoying - links don't always preview well, and there's no built-in download. This bot makes it instant: paste URL, get video/image.

## How It Works

1. User sends a URL to the bot
2. Bot detects the platform (YouTube/TikTok/Instagram)
3. yt-dlp downloads the media via subprocess
4. Bot uploads the file to Telegram
5. Temp files are cleaned up

## Docs

| Document | What it covers |
|---|---|
| [Architecture](architecture.md) | Module responsibilities, data flow, design decisions |
| [Design Spec](superpowers/specs/2026-05-27-media-downloader-bot-design.md) | Original requirements and design |
| [Implementation Plan](superpowers/plans/2026-05-27-media-downloader-bot.md) | Step-by-step build plan with TDD |

## Quick Start

```bash
cp .env.example .env
# Edit .env with your BOT_TOKEN from @BotFather
pip install -r requirements.txt
python bot.py
```

Or with Docker:
```bash
cp .env.example .env
./compose.sh
```
