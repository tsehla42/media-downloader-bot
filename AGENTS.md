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
│   ├── guest.py        # Bot API 10.0 guest mode: handle_guest(), download pipeline, InlineQueryResult builders
│   ├── auth.py         # Authorization checks (is_authorized, is_group_chat, allowlists)
│   ├── commands.py     # User commands: /start, /help, /caption
│   ├── telegram_utils.py # Telegram helpers: typing_indicator, send_images
│   ├── logging_config.py # Structured JSON logging with three-file split (requests, details, service)
│   ├── platforms/       # Platform-specific download logic
│   │   ├── __init__.py # detect_platform(), extract_domain(), SUPPORTED_PLATFORMS dict
│   │   ├── youtube.py  # YouTube/YT Music download + format picker callback
│   │   ├── tiktok.py   # TikTok download with gallery-dl fallback
│   │   └── instagram.py # Instagram images with gallery-dl fallback
│   └── utils.py        # URL validation, file cleanup, get_gallery_dl_domains()
├── scripts/            # Utility scripts
│   └── generate_gallery_dl_domains.py # Fetches gallery-dl supported sites, writes domain whitelist
├── tests/              # Test suite (imports from src/ via conftest.py)
│   ├── test_handlers.py
│   ├── test_commands.py
│   ├── test_auth.py
│   ├── test_telegram_utils.py
│   ├── test_youtube.py
│   ├── test_tiktok.py
│   ├── test_guest.py
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
| `src/config.py` | .env file, allowed-contacts.json | Loads BOT_TOKEN, BOT_ADMIN_IDS, ALLOWED_USER_IDS (merged from JSON + env), ALLOWED_GROUP_IDS, DOWNLOAD_DIR, MAX_FILE_SIZE, INSTAGRAM_COOKIES, GUEST_MODE_ENABLED, STORAGE_CHANNEL_ID, MODE, LOG_OUTPUT, LOG_DIR, LOG_LEVEL |
| `src/auth.py` | config | Authorization: `is_authorized()`, `is_bot_admin()`, `was_notified()`, `mark_notified()`, `was_notified_guest()`, `mark_notified_guest()`, `is_group_chat()`, `_is_allowed()`, `_is_allowed_group()` |
| `src/commands.py` | auth, config, logging_config | User commands: `start_command()`, `help_command()`, `caption_command()`, `get_caption_for_user()` — all use notification tracking for unauthorized users |
| `src/telegram_utils.py` | nothing | Telegram helpers: `typing_indicator()` context manager, `send_images()` for single/batched photo replies |
| `src/platforms/__init__.py` | nothing | Platform detection: `detect_platform()`, `extract_domain()`, `SUPPORTED_PLATFORMS` dict |
| `src/platforms/youtube.py` | downloader, commands, telegram_utils | YouTube/YT Music: `handle_youtube()`, `handle_ytmusic()`, `ytmusic_callback()`, format picker |
| `src/platforms/tiktok.py` | downloader, telegram_utils | TikTok: `handle_tiktok()` with gallery-dl fallback for photo posts |
| `src/platforms/instagram.py` | downloader, telegram_utils | Instagram: `handle_instagram()` with gallery-dl fallback and cookies |
| `src/utils.py` | nothing | URL validation, file cleanup, `get_gallery_dl_domains()` (imports/auto-generates gallery-dl domain whitelist) |
| `src/downloader.py` | yt-dlp, gallery-dl | yt-dlp subprocess calls: `get_metadata()`, `download_video()`, `download_audio()`, `download_images()`, `download_gallery_dl_images()`, `download_gallery_dl_video()` |
| `src/logging_config.py` | config | Structured JSON logging: three-file split (requests/details/service), JSONFormatter, filter-based routing, with_request_logging decorator, contextvars for request_id, request lifecycle functions (log_request_received/completed/failed), guest request functions (log_guest_request_received/completed), service log functions (log_new_user, log_bot_added_to_chat, log_bot_rejected_group_addition, log_bot_removed_from_chat, log_admin_rights_changed, log_user_blocked_bot, log_unauthorized_access) |
| `src/handlers.py` | auth, commands, platforms, telegram_utils, downloader, logging_config | Thin orchestrator: `handle_url()` (includes reply-to-retry, gallery-dl fallback, and unauthorized reply-to-bot check in groups), `handle_gallery_dl_fallback()`, `audio_command()`, `_download_and_send()`, `my_chat_member_handler()` (handles bot added/removed/promoted/demoted/blocked, admin check for group additions) |
| `src/guest.py` | auth, config, downloader, platforms, utils, logging_config, httpx | Bot API 10.0 guest mode: `handle_guest()` receives guest_message updates, extracts URLs (from tag text or replied-to message), downloads via platform handlers, uploads to storage channel for file_id, replies via `answer_guest_query()`. Uses raw dicts for InlineQueryResult to avoid ptb placeholder URL issues. Unauthorized users get "You are not authorized" once via `answer_guest_query`, then silently ignored. Uses `was_notified_guest()`/`mark_notified_guest()` (separate from P2P tracking). Reply to bot message without URL is silently ignored. Logs unauthorized access to service.jsonl via `log_unauthorized_access()`. For gallery-dl supported domains (e.g. deviantart, pinterest), falls back to `_gallery_dl_result()` when platform is not in SUPPORTED_PLATFORMS. Platform logged from `extract_domain(url)` for non-primary platforms. Photo upload handles Telegram's list-of-PhotoSize response. |
| `src/bot.py` | config, handlers, commands, platforms.youtube, logging_config, guest | Entry point, wires everything together, initializes logging, global error handler. Guest handler registered BEFORE text handler (filters.TEXT matches guest messages via effective_message). |

## Data Flow

1. User sends URL or `/audio` command -> `handlers.py` routes to appropriate handler
2. **Authorization check**: `is_authorized(update)` called at start of every handler:
   - **Groups**: always allowed (bot only exists if admin added it)
   - **P2P**: checks `ALLOWED_USER_IDS` (empty sources = allow all; configured sources = user must be in list)
   - **Unauthorized P2P**: first attempt → "You are not authorized" + `log_unauthorized_access` event; subsequent → silently ignored
3. `/audio` → `audio_command()` → `download_audio()` → `reply_audio()` (logged via `@with_request_logging`)
3. Regular URL → `handle_url()` detects group or P2P chat via `is_group_chat()`
4. URLs split into `supported_urls` (YT/TT/IG) and `unsupported_urls` (everything else)
5. Unsupported URLs filtered against gallery-dl domain whitelist (`get_gallery_dl_domains()`). Domains not in the list are skipped instantly (logged as `success: false` with platform set to domain)
6. YouTube URLs: metadata fetched silently (no typing indicator), size checked against 50MB limit
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
    - Reply-to-retry uses `"event": "reply_to_retry_received"` / `"reply_to_retry_completed"` to differentiate from normal requests
11. Intermediate download steps (yt-dlp calls, retries, gallery-dl attempts) logged to `request-details.jsonl` via `details_logger`
12. Bot start/stop, chat membership, new user events logged to `service.jsonl` via `service_logger`
13. `my_chat_member_handler` (registered via `ChatMemberHandler`):
    - Bot added to group: checks `is_bot_admin(from_user.id)` → admin: log + allow; non-admin: `log_bot_rejected_group_addition` + reject + leave
    - Bot removed/promoted/demoted: logged to service.jsonl
    - User blocks bot (private chat): logged as `user_blocked_bot`
14. **Guest mode** (`GUEST_MODE_ENABLED=true`): User mentions `@botname` in any chat → Telegram sends `guest_message` update → `guest.handle_guest()`:
    - Caller identified via `guest_msg.from_user` (Telegram sends `from`, ptb maps to `from_user`)
    - Auth check via `is_user_allowed(caller_id)` (same allowlist as regular messages)
    - **Unauthorized guest**: first attempt → "You are not authorized" via `answer_guest_query` + `log_unauthorized_access` to service.jsonl; subsequent → silently ignored. Uses `was_notified_guest()`/`mark_notified_guest()` (separate from P2P tracking)
    - URL extracted from tag text OR replied-to message
    - Reply to bot message without URL → silently ignored (no error message)
    - Reply to bot message with no text → shows media type (e.g. `[photo]`, `[video]`) in logs
    - `log_guest_request_received()` logs to `requests.jsonl` with user, chat, reply context
    - Platform detected via `detect_platform()`. If None, falls back to `extract_domain(url)` for logging (e.g. "deviantart.com")
    - Download routed via `_download_and_build_result()`:
      - YouTube → `_download_youtube()`
      - TikTok/Instagram → `_download_media_result()`
      - Gallery-dl supported domain → `_gallery_dl_result()` (checks `get_gallery_dl_domains()` whitelist)
      - Unsupported domain → "Unsupported platform"
    - File uploaded to storage channel (`STORAGE_CHANNEL_ID`) to get `file_id`. Photo responses handled as list (Telegram sends PhotoSize array).
    - Reply via `answer_guest_query()` with InlineQueryResult (raw dict with `video_file_id`/`photo_file_id`). Single photo only — inline results don't support media groups.
    - `log_guest_request_completed()` logs success/failure, platform, duration to `requests.jsonl`
    - **Handler order**: guest handler registered BEFORE text handler because `filters.TEXT` matches guest messages via `effective_message`
15. **Unauthorized reply to bot in groups**: In `handle_url()`, if a user replies to a bot message in a group and is not in the allowlist (`_is_allowed()`), the message is silently ignored. This prevents unauthorized users from triggering downloads by replying to bot messages in groups.

## Key Design Decisions

- **yt-dlp as subprocess** - Not imported as Python library. Keeps yt-dlp independently upgradable.
- **Stateless bot** - No database. Temp files cleaned after upload. Notification tracking (`_already_told_users`) resets on restart.
- **Auto best quality** - Downloads best quality under 50MB Telegram limit, retries with worst on failure.
- **User allowlist** - IDs merged from `allowed-contacts.json` (array of objects with `id` field) + `ALLOWED_USER_IDS` env var. If no sources configured = allow all. If sources configured but user not in list = deny.
- **Bot admins** - `BOT_ADMIN_IDS` env var (comma-separated). Admins can add bot to groups. Empty = anyone can add.
- **Unauthorized user handling** - First attempt: "You are not authorized" + log `unauthorized_access` event. Subsequent attempts: silently ignored (in-memory sets, resets on restart). P2P and guest mode track separately — a user told in P2P can still use guest mode and vice versa.
- **Group security** - Only bot admins can add bot to groups (checked in `my_chat_member_handler`). Non-admin additions rejected with message + bot leaves.
- **Structured logging** - Three JSON log files: `requests.jsonl` (request lifecycle), `request-details.jsonl` (intermediate download steps), `service.jsonl` (bot events). Filter-based routing by logger name. Zero external dependencies.
- **Docker deployment** - Multi-stage build with yt-dlp, gallery-dl, and ffmpeg. Persistent logs via volume mount to `./logs/`. `allowed-contacts.json` mounted read-only.
- **Platform separation** - Each platform (YouTube, TikTok, Instagram) has its own module with isolated download logic.
- **Guest mode (Bot API 10.0)** - Users mention `@botname` in any chat to download media. Uses `guest_message` updates + `answerGuestQuery()`. Files uploaded to a private storage channel to get `file_id`s for InlineQueryResult. Guest handler registered before text handler to prevent `filters.TEXT` from consuming guest updates.
- **InlineQueryResult as raw dicts** - ptb's `InlineQueryResultVideo`/`Photo` constructors require placeholder URLs that Telegram tries to fetch. Using raw dicts with `video_file_id`/`photo_file_id` avoids this.

## Security Rules

**NEVER** `git add`, `git commit`, or `git push` files under `docs/superpowers/` (specs, plans, design docs). These are internal AI working documents and must NEVER enter git history.

Never commit `allowed-contacts.json` — it contains user IDs and is generated locally by the get-contact-ids script.

## Running Tests

```bash
python -m pytest tests/ -v
```

All 291 tests use mocked subprocess calls - no real downloads needed.

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

- [Project Overview](docs/README.md) - Quick summary of what/why, architecture, and links to detailed docs
- [Guest Mode](docs/guest-mode/README.md) - Bot API 10.0 guest mode overview and technical reference
- [Deployment](docs/deploy.md) - Production server deployment flow
