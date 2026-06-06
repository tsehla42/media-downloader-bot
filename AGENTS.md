# Agents Guide

Entry point for AI agents working on this project. Start here to understand the codebase before making changes.

## What This Project Is

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram. Users paste a URL, get the media back. Also silently attempts gallery-dl for 100+ other services (Pinterest, Pixiv, X, Reddit, DeviantArt, etc.) — works as a best-effort fallback.

**Tech stack:** Python 3.12+, python-telegram-bot, yt-dlp (subprocess), gallery-dl (subprocess), pytest

## Project Structure

```
media-downloader-bot/
├── src/                # Application code
│   ├── bot.py          # Entry point - creates Application, registers handlers, runs polling
│   ├── config.py       # Loads .env, exports settings as constants
│   ├── downloader.py   # yt-dlp subprocess wrapper (metadata, download, audio, images)
│   ├── handlers.py     # Telegram handlers: /audio, URL message handling (thin orchestrator)
│   ├── auth.py         # Authorization checks (is_authorized, is_group_chat, allowlists)
│   ├── commands.py     # User commands: /start, /help, /caption
│   ├── telegram_utils.py # Telegram helpers: typing_indicator, send_images
│   ├── logging_config.py # Structured JSON logging with three-file split (requests, details, service)
│   ├── platforms/       # Platform-specific download logic
│   │   ├── __init__.py # detect_platform(), SUPPORTED_PLATFORMS dict
│   │   ├── youtube.py  # YouTube/YT Music download + format picker callback
│   │   ├── tiktok.py   # TikTok download with gallery-dl fallback
│   │   └── instagram.py # Instagram images with gallery-dl fallback
│   └── utils.py        # URL validation, file cleanup
├── tests/              # Test suite (imports from src/ via conftest.py)
│   ├── test_handlers.py
│   ├── test_commands.py
│   ├── test_auth.py
│   ├── test_telegram_utils.py
│   ├── test_youtube.py
│   ├── test_tiktok.py
│   ├── test_downloader.py
│   └── test_logging.py
├── docs/
│   ├── README.md       # Project overview
│   └── architecture.md # Module responsibilities and data flow
├── logs/               # Persistent log files (gitignored, mounted as volume)
├── requirements.txt    # Dependencies
├── .env.example        # Config template
├── Dockerfile          # Multi-stage build (Python 3.12-slim, yt-dlp, gallery-dl, ffmpeg)
├── docker-compose.yml  # Container orchestration with volume mounts
├── .dockerignore       # Excludes .venv, __pycache__, logs, cookies.txt from build
├── compose.sh          # Build + deploy script
└── conftest.py         # Adds src/ to Python path for tests
```

## Module Responsibilities

| Module | Depends on | What it does |
|---|---|---|
| `src/config.py` | .env file | Loads BOT_TOKEN, ALLOWED_USER_IDS, ALLOWED_GROUP_IDS, DOWNLOAD_DIR, MAX_FILE_SIZE, INSTAGRAM_COOKIES, MODE, LOG_OUTPUT, LOG_DIR |
| `src/auth.py` | config | Authorization: `is_authorized()`, `is_group_chat()`, `_is_allowed()`, `_is_allowed_group()` |
| `src/commands.py` | auth, config, logging_config | User commands: `start_command()`, `help_command()`, `caption_command()`, `get_caption_for_user()` |
| `src/telegram_utils.py` | nothing | Telegram helpers: `typing_indicator()` context manager, `send_images()` for single/batched photo replies |
| `src/platforms/__init__.py` | nothing | Platform detection: `detect_platform()`, `SUPPORTED_PLATFORMS` dict |
| `src/platforms/youtube.py` | downloader, commands, telegram_utils | YouTube/YT Music: `handle_youtube()`, `handle_ytmusic()`, `ytmusic_callback()`, format picker |
| `src/platforms/tiktok.py` | downloader, telegram_utils | TikTok: `handle_tiktok()` with gallery-dl fallback for photo posts |
| `src/platforms/instagram.py` | downloader, telegram_utils | Instagram: `handle_instagram()` with gallery-dl fallback and cookies |
| `src/utils.py` | nothing | URL validation, file cleanup |
| `src/downloader.py` | yt-dlp, gallery-dl | yt-dlp subprocess calls: `get_metadata()`, `download_video()`, `download_audio()`, `download_images()`, `download_gallery_dl_images()`, `download_gallery_dl_video()` |
| `src/logging_config.py` | config | Structured JSON logging: three-file split (requests/details/service), JSONFormatter, filter-based routing, with_request_logging decorator, contextvars for request_id, service log functions (log_new_user, log_bot_added_to_chat, log_bot_removed_from_chat, log_admin_rights_changed, log_user_blocked_bot) |
| `src/handlers.py` | auth, commands, platforms, telegram_utils, downloader | Thin orchestrator: `handle_url()` (includes reply-to-retry and gallery-dl fallback), `handle_gallery_dl_fallback()`, `audio_command()`, `_download_and_send()`, `my_chat_member_handler()` (handles bot added/removed/promoted/demoted/blocked) |
| `src/bot.py` | config, handlers, commands, platforms.youtube, logging_config | Entry point, wires everything together, initializes logging, global error handler |

## Data Flow

1. User sends URL or `/audio` command -> `handlers.py` routes to appropriate handler
2. `/audio` → `audio_command()` → `download_audio()` → `reply_audio()` (logged via `@with_request_logging`)
3. Regular URL → `handle_url()` detects group or P2P chat via `is_group_chat()`
4. URLs split into `supported_urls` (YT/TT/IG) and `unsupported_urls` (everything else)
5. YouTube URLs: metadata fetched silently (no typing indicator), size checked against 50MB limit
6. Reply-to-retry: user replies to message with URL and mentions bot → handled inside `handle_url()` (extracts URL from replied message, retries download)
7. `handlers.py` detects platform via `platforms.detect_platform()`
8. Delegates to platform-specific handler:
   - YouTube → `platforms.youtube.handle_youtube()` or `handle_ytmusic()`
   - TikTok → `platforms.tiktok.handle_tiktok()` (with gallery-dl fallback)
   - Instagram → `platforms.instagram.handle_instagram()` (with gallery-dl fallback)
9. Unsupported URLs → `handle_gallery_dl_fallback()`:
   - Tries `download_gallery_dl_images()` first, then `download_gallery_dl_video()`
   - If content found, sends to Telegram (silent on success)
   - If nothing works: silent in groups, "Unsupported platform" in P2P
   - Sets `platform` in logs from URL domain (e.g. "deviantart", "pinterest")
10. `@with_request_logging` decorator logs request lifecycle automatically:
   - `request_received` when handler starts (in `requests.jsonl`)
   - `request_completed` when handler finishes (success or expected failure) (in `requests.jsonl`)
   - `request_failed` when handler throws exception (in `requests.jsonl`)
   - Reply-to-retry uses `"event": "reply_to_retry"` to differentiate from normal requests
11. Intermediate download steps (yt-dlp calls, retries, gallery-dl attempts) logged to `request-details.jsonl` via `details_logger`
12. Bot start/stop, chat membership, new user events logged to `service.jsonl` via `service_logger`
13. `my_chat_member_handler` (registered via `ChatMemberHandler`) logs: bot added/removed from chat, admin added/removed with rights, admin rights changed (with delta), user blocks bot (private chat)

## Key Design Decisions

- **yt-dlp as subprocess** - Not imported as Python library. Keeps yt-dlp independently upgradable.
- **Stateless bot** - No database. Temp files cleaned after upload.
- **Auto best quality** - Downloads best quality under 50MB Telegram limit, retries with worst on failure.
- **User allowlist** - ALLOWED_USER_IDS from `allowed_contacts.json` (generated by separate get-contact-ids project). Fallback to .env. Empty = allow all.
- **Group auto-detect** - Bot silently ignores unsupported URLs in groups. Optional ALLOWED_GROUP_IDS restricts which groups.
- **Structured logging** - Three JSON log files: `requests.jsonl` (request lifecycle), `request-details.jsonl` (intermediate download steps), `service.jsonl` (bot events). Filter-based routing by logger name. Zero external dependencies.
- **Docker deployment** - Multi-stage build with yt-dlp, gallery-dl, and ffmpeg. Persistent logs via volume mount to `./logs/`.
- **Platform separation** - Each platform (YouTube, TikTok, Instagram) has its own module with isolated download logic.

## Security Rules

**NEVER** `git add`, `git commit`, or `git push` files under `docs/superpowers/` (specs, plans, design docs). These are internal AI working documents and must NEVER enter git history.

Never commit `allowed_contacts.json` — it contains user IDs and is generated locally by the get-contact-ids script.

## Running Tests

```bash
python -m pytest tests/ -v
```

All 216 tests use mocked subprocess calls - no real downloads needed.

## Common Tasks

**Add a new platform:** Create `src/platforms/newplatform.py` with a `handle_newplatform()` function, add domain to `SUPPORTED_PLATFORMS` in `src/platforms/__init__.py`, add platform-specific args in `src/downloader.py`. Register in `handlers.py` `_download_and_send()`.

**Add a new command:** Add handler function in `src/commands.py`, register in `src/bot.py` with `app.add_handler(CommandHandler(...))`.

**Change download behavior:** Edit `src/downloader.py` for yt-dlp changes, or the platform-specific handler in `src/platforms/` for platform logic.

**Add logging to a handler:** Apply `@with_request_logging` decorator from `logging_config`. The decorator automatically logs request lifecycle (received/completed/failed).

**Setup for groups:** Disable privacy mode in @BotFather (`/setprivacy` → Disable). Optionally set `ALLOWED_GROUP_IDS` in .env to restrict which groups. Add bot to target groups.

**Run with Docker:**
```bash
cp .env.example .env  # Add BOT_TOKEN
docker compose up -d --build
docker logs -f media-downloader-bot  # Watch logs
```

**View persistent logs:** Logs are written to `./logs/` on the host (mounted as volume). Files: `requests.jsonl` (request lifecycle), `request-details.jsonl` (download steps), `service.jsonl` (bot events). Append `.dev.jsonl` for MODE=development.

**Deploy to production:** Read `docs/deploy.md` for the full deployment flow.
When asked to "update bot" or "deploy", always read `docs/deploy.md` first.

## Docs Index

- [Project Overview](docs/README.md) - Quick summary of what/why
- [Architecture](docs/architecture.md) - Detailed module responsibilities and data flow
- [Deployment](docs/deploy.md) - Production server deployment flow
