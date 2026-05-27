# Agents Guide

Entry point for AI agents working on this project. Start here to understand the codebase before making changes.

## What This Project Is

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram. Users paste a URL, get the media back. Also supports inline queries (`@botname <url>`) in any chat.

**Tech stack:** Python 3.12+, python-telegram-bot, yt-dlp (subprocess), pytest

## Project Structure

```
media-downloader-bot/
├── bot.py              # Entry point - creates Application, registers handlers, runs polling
├── config.py           # Loads .env, exports settings as constants
├── downloader.py       # yt-dlp subprocess wrapper (metadata, download, audio, images)
├── handlers.py         # Telegram handlers: /start, /help, /audio, URL message handling
├── inline.py           # Inline query handler for @botname usage
├── utils.py            # Platform detection, URL validation, file cleanup
├── requirements.txt    # Dependencies
├── .env.example        # Config template
├── Dockerfile          # Multi-stage build
├── docker-compose.yml  # Container orchestration
├── compose.sh          # Build + deploy script
├── tests/              # Test suite
│   ├── test_utils.py
│   ├── test_downloader.py
│   └── test_handlers.py
└── docs/
    ├── README.md       # Project overview
    ├── architecture.md # Module responsibilities and data flow
    └── superpowers/    # Design specs and implementation plans
```

## Module Responsibilities

| Module | Depends on | What it does |
|---|---|---|
| `config.py` | .env file | Loads BOT_TOKEN, ALLOWED_USER_IDS, DOWNLOAD_DIR, MAX_FILE_SIZE |
| `utils.py` | nothing | Platform detection from URL, URL validation, file cleanup |
| `downloader.py` | nothing | yt-dlp subprocess calls: get_metadata, download_video, download_audio, download_images |
| `handlers.py` | config, utils, downloader | Telegram message handlers, orchestrates download flow |
| `inline.py` | config, utils, downloader | Inline query handler, returns metadata as inline results |
| `bot.py` | config, handlers, inline | Entry point, wires everything together |

## Data Flow

1. User sends URL -> `handlers.py` detects platform via `utils.detect_platform()`
2. `handlers.py` calls `downloader.get_metadata()` to fetch title/thumbnail
3. `handlers.py` calls `downloader.download_video()` or `download_audio()` or `download_images()`
4. `handlers.py` sends file to Telegram, cleans up temp files

## Key Design Decisions

- **yt-dlp as subprocess** - Not imported as Python library. Keeps yt-dlp independently upgradable.
- **Stateless bot** - No database. Temp files cleaned after upload.
- **Auto best quality** - Downloads best quality under 50MB Telegram limit, retries with worst on failure.
- **User allowlist** - ALLOWED_USER_IDS in .env. Empty = allow all.

## Running Tests

```bash
python -m pytest tests/ -v
```

All 19 tests use mocked subprocess calls - no real downloads needed.

## Common Tasks

**Add a new platform:** Add domain to `SUPPORTED_PLATFORMS` in `utils.py`, add platform-specific args in `downloader.py`.

**Add a new command:** Add handler function in `handlers.py`, register in `bot.py` with `app.add_handler(CommandHandler(...))`.

**Change download behavior:** Edit `downloader.py`. All yt-dlp calls go through `subprocess.run()`.

## Docs Index

- [Project Overview](docs/README.md) - Quick summary of what/why
- [Architecture](docs/architecture.md) - Detailed module responsibilities and data flow
- [Design Spec](docs/superpowers/specs/2026-05-27-media-downloader-bot-design.md) - Original design document
- [Implementation Plan](docs/superpowers/plans/2026-05-27-media-downloader-bot.md) - Step-by-step build plan
