# Agents Guide

Entry point for AI agents working on this project. Start here to understand the codebase before making changes.

## What This Project Is

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram. Users paste a URL, get the media back.

**Tech stack:** Python 3.12+, python-telegram-bot, yt-dlp (subprocess), pytest

## Project Structure

```
media-downloader-bot/
├── src/                # Application code
│   ├── bot.py          # Entry point - creates Application, registers handlers, runs polling
│   ├── config.py       # Loads .env, exports settings as constants
│   ├── downloader.py   # yt-dlp subprocess wrapper (metadata, download, audio, images)
│   ├── handlers.py     # Telegram handlers: /start, /help, /audio, URL message handling
│   ├── logging_config.py # Structured JSON logging (JSONFormatter, with_request_logging decorator)
│   └── utils.py        # Platform detection, URL validation, file cleanup
├── tests/              # Test suite (imports from src/ via conftest.py)
│   ├── test_utils.py
│   ├── test_downloader.py
│   ├── test_handlers.py
│   └── test_logging.py # Logging infrastructure tests
├── docs/
│   ├── README.md       # Project overview
│   ├── architecture.md # Module responsibilities and data flow
│   └── superpowers/    # Design specs and implementation plans
├── requirements.txt    # Dependencies
├── .env.example        # Config template
├── Dockerfile          # Multi-stage build
├── docker-compose.yml  # Container orchestration
├── compose.sh          # Build + deploy script
└── conftest.py         # Adds src/ to Python path for tests
```

## Module Responsibilities

| Module | Depends on | What it does |
|---|---|---|
| `src/config.py` | .env file | Loads BOT_TOKEN, ALLOWED_USER_IDS, DOWNLOAD_DIR, MAX_FILE_SIZE, LOG_OUTPUT, LOG_DIR |
| `src/utils.py` | nothing | Platform detection from URL, URL validation, file cleanup |
| `src/downloader.py` | nothing | yt-dlp subprocess calls: get_metadata, download_video, download_audio, download_images |
| `src/logging_config.py` | config | Structured JSON logging: JSONFormatter, setup_logging, with_request_logging decorator |
| `src/handlers.py` | config, utils, downloader, logging_config | Telegram message handlers, orchestrates download flow, logs requests |
| `src/bot.py` | config, handlers, logging_config | Entry point, wires everything together, initializes logging |

## Data Flow

1. User sends URL -> `handlers.py` detects platform via `utils.detect_platform()`
2. `handlers.py` calls `downloader.get_metadata()` to fetch title/thumbnail
3. `handlers.py` calls `downloader.download_video()` or `download_audio()` or `download_images()`
4. `handlers.py` sends file to Telegram, cleans up temp files
5. `@with_request_logging` decorator logs request lifecycle automatically:
   - `request_received` when handler starts
   - `request_completed` when handler finishes (success or expected failure)
   - `request_failed` when handler throws exception

## Key Design Decisions

- **yt-dlp as subprocess** - Not imported as Python library. Keeps yt-dlp independently upgradable.
- **Stateless bot** - No database. Temp files cleaned after upload.
- **Auto best quality** - Downloads best quality under 50MB Telegram limit, retries with worst on failure.
- **User allowlist** - ALLOWED_USER_IDS in .env. Empty = allow all.
- **Structured logging** - JSON logs for easy querying. stdout for dev, rotating files for prod. Zero external dependencies.

## Running Tests

```bash
python -m pytest tests/ -v
```

All 34 tests use mocked subprocess calls - no real downloads needed.

## Common Tasks

**Add a new platform:** Add domain to `SUPPORTED_PLATFORMS` in `src/utils.py`, add platform-specific args in `src/downloader.py`.

**Add a new command:** Add handler function in `src/handlers.py`, register in `src/bot.py` with `app.add_handler(CommandHandler(...))`.

**Change download behavior:** Edit `src/downloader.py`. All yt-dlp calls go through `subprocess.run()`.

**Add logging to a handler:** Apply `@with_request_logging` decorator from `logging_config`. The decorator automatically logs request lifecycle (received/completed/failed).

## Docs Index

- [Project Overview](docs/README.md) - Quick summary of what/why
- [Architecture](docs/architecture.md) - Detailed module responsibilities and data flow
- [Design Spec](docs/superpowers/specs/2026-05-27-media-downloader-bot-design.md) - Original design document
- [Implementation Plan](docs/superpowers/plans/2026-05-27-media-downloader-bot.md) - Step-by-step build plan
- [Structured Logging Spec](docs/superpowers/specs/2026-05-28-structured-logging-design.md) - Logging system design
- [Structured Logging Plan](docs/superpowers/plans/2026-05-28-structured-logging.md) - Logging implementation plan
- [Split Logging Spec](docs/superpowers/specs/2026-05-29-split-logging-design.md) - Request lifecycle logging design
- [Split Logging Plan](docs/superpowers/plans/2026-05-29-split-logging.md) - Request lifecycle logging implementation plan
