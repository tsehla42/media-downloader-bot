# Architecture

## Overview

Modular design. Each module has one clear responsibility. yt-dlp is called as a subprocess, not imported as a library.

## Modules

### config.py
Loads settings from `.env` via python-dotenv. Exports constants:
- `BOT_TOKEN` - Telegram bot token
- `BOT_ADMIN_IDS` - Comma-separated admin user IDs (empty = anyone can add bot to groups)
- `ALLOWED_USER_IDS` - Merged from `allowed-contacts.json` (array of objects with `id` field) + env var. Empty sources = allow all; configured sources = user must be in list.
- `ALLOWED_IDS_CONFIGURED` - Boolean: True if any ID source (JSON file or env var) exists
- `ALLOWED_GROUP_IDS` - Comma-separated group chat IDs (empty = allow all groups)
- `DOWNLOAD_DIR` - Temp directory for downloads (default: /tmp/bot-downloads)
- `MAX_FILE_SIZE` - Max download size in MB (default: 50)
- `MAX_CONCURRENT_DOWNLOADS` - Concurrency limit (default: 3)
- `INSTAGRAM_COOKIES` - Path to cookies.txt for gallery-dl Instagram auth (empty = no auth)
- `MODE` - Environment mode: "development" (default) or "production". Determines log file name.
- `LOG_OUTPUT` - Logging destination: "console", "file", or "both" (default). "stdout" is an alias for "console".
- `LOG_DIR` - Log file directory (default: logs)

### auth.py
Authorization checks, depends on config:
- `is_authorized(update)` - Groups: always allowed (bot only exists if admin added it). P2P: checks ALLOWED_USER_IDS (empty sources = allow all; configured sources = user must be in list).
- `is_bot_admin(user_id)` - Checks if user is in BOT_ADMIN_IDS (empty = allow all)
- `was_notified(user_id)` - Checks if user has been told they're not authorized (in-memory set)
- `mark_notified(user_id)` - Marks user as notified (resets on restart)
- `is_group_chat(update)` - Checks if message is from group/supergroup
- `_is_allowed(user_id)` - Checks if user is in allowlist (no sources = allow all; sources configured but empty = deny all)
- `_is_allowed_group(chat_id)` - Checks if group is in allowlist (empty = allow all)

### commands.py
User-facing commands, depends on auth, config, logging_config:
- `_user_caption_prefs` - Per-user caption preferences dict (user_id -> bool)
- `get_caption_for_user(user_id, title)` - Returns caption string based on preference (empty if disabled)
- `start_command(update, context)` - Welcome message (uses notification tracking for unauthorized users)
- `help_command(update, context)` - Supported platforms and commands list (uses notification tracking)
- `caption_command(update, context)` - Toggle video captions on/off (uses notification tracking)

### telegram_utils.py
Telegram helper utilities, no dependencies:
- `typing_indicator(chat_id, bot)` - Async context manager that shows typing indicator while active
- `send_images(message, images, reply_params)` - Sends single photo or batched media groups, returns total size in bytes

### platforms/__init__.py
Platform detection and registry, no dependencies:
- `SUPPORTED_PLATFORMS` - Dict mapping platform names to their domains
- `detect_platform(url)` - Returns "youtube", "tiktok", "instagram", or None

### platforms/youtube.py
YouTube and YouTube Music download logic, depends on downloader, commands, telegram_utils:
- `_has_video_available(metadata)` - Checks if metadata indicates video (not audio-only)
- `_download_and_send_video(url, base, output_path, caption, reply_params, message, context)` - Downloads and sends video
- `_store_download_metadata(context, content_type, file_path)` - Stores download metadata for logging
- `handle_youtube(update, context, url)` - Handles regular YouTube URLs
- `handle_ytmusic(update, context, url, metadata, title, base, output_path, reply_params)` - Handles YouTube Music (format picker or audio-only)
- `ytmusic_callback(update, context)` - Handles format picker callback (Audio/Video/Video+Audio)
- `_ytmusic_pending` - Shared dict for pending format requests
- `AUDIO_TITLE_MAX` - Telegram Bot API limit for audio title (64 chars)

### platforms/tiktok.py
TikTok download logic with gallery-dl fallback, depends on downloader, telegram_utils:
- `handle_tiktok(update, context, url)` - Checks metadata for photo posts (best-effort), tries video download, falls back to gallery-dl

### platforms/instagram.py
Instagram download logic with gallery-dl fallback, depends on downloader, telegram_utils:
- `handle_instagram(update, context, url)` - Handles both metadata-success (yt-dlp) and metadata-failure (gallery-dl with cookies) paths

### utils.py
Pure utility functions, no dependencies:
- `is_valid_url(text)` - Checks for HTTP(S) URL pattern
- `extract_urls(text)` - Finds all URLs in text
- `ensure_download_dir(path)` - Creates download directory if needed
- `cleanup_file(path)` / `cleanup_dir(path)` - Safe file removal

### downloader.py
Wraps yt-dlp and gallery-dl binary calls via subprocess:
- `_find_ytdlp()` / `_find_gallery_dl()` - Locate binaries
- `get_metadata(url)` - Runs `yt-dlp --dump-json`, returns dict with title/thumbnail/duration
- `download_video(url, path, max_size, platform)` - Downloads video, retries with lower quality on failure
- `download_audio(url, path)` - Extracts audio as MP3
- `download_images(url, dir)` - Downloads carousel/gallery images via gallery-dl
- `download_gallery_dl_images(url, dir, cookies)` - Downloads images using gallery-dl
- `download_gallery_dl_video(url, dir)` - Downloads video using gallery-dl (for unsupported platform fallback)

### handlers.py
Thin orchestrator, depends on auth, commands, platforms, telegram_utils, downloader, logging_config:
- `my_chat_member_handler(update, context)` - Handles bot membership changes. When bot added to group: checks `is_bot_admin(from_user.id)` → admin: log + allow; non-admin: `log_bot_rejected_group_addition` + reject message + leave. Also handles removed/promoted/demoted/blocked events.
- `audio_command(update, context)` - Download as MP3 (uses notification tracking for unauthorized users)
- `_download_and_send(update, context, url, silent, reply_to_message_id)` - Orchestrates download with YouTube size check and error suppression
- `handle_gallery_dl_fallback(update, context, url)` - Tries gallery-dl for unsupported platforms (images then video), silent on failure
- `handle_url(update, context)` - Main handler: authorization check, detects group/P2P, splits supported/unsupported URLs, handles reply-to-retry, routes unsupported URLs to gallery-dl fallback

### logging_config.py
Structured JSON logging with zero external dependencies:
- `JSONFormatter` - Custom `logging.Formatter` that outputs JSON with timestamp (Europe/Kyiv timezone)
- `RequestsFilter` / `DetailsFilter` / `ServiceFilter` - `logging.Filter` subclasses that route by logger name
- `requests_logger` / `details_logger` / `service_logger` - Module-level logger instances
- `set_current_request_id()` / `get_current_request_id()` - ContextVar for passing request_id to downloader/platform code
- `_resolve_log_file(mode)` / `_resolve_detail_log_file(mode)` / `_resolve_service_log_file(mode)` - Maps MODE to log filenames
- `setup_logging()` - Creates three `RotatingFileHandler` instances with filters + console handler
- `with_request_logging()` - Decorator that wraps handlers and logs request lifecycle
- `log_request_received()` / `log_request_completed()` / `log_request_failed()` - Log request events (use `requests_logger`)
- `log_new_user()` / `log_bot_added_to_chat()` / `log_bot_rejected_group_addition()` / `log_bot_removed_from_chat()` / `log_admin_rights_changed()` / `log_user_blocked_bot()` / `log_unauthorized_access()` - System events (use `service_logger`)
- `_extract_admin_rights(member)` - Extracts admin rights dict from ChatMemberAdministrator

### bot.py
Entry point:
- Creates `Application` with bot token
- Registers all handlers
- Starts polling
- Global `error_handler` for unhandled exceptions

## Data Flow

```
User sends URL or /audio command
    │
    ▼
handlers.handle_url()
    │
    ├─ /audio → audio_command() → download_audio() → reply_audio()
    │   (logged via @with_request_logging)
    │
    ├─ Reply to message + bot mention? → reply-to-retry flow
    │   └─ Extract URL from replied message → _download_and_send(silent=False)
    │
    ├─ Split URLs into supported (YT/TT/IG) and unsupported
    │
    ├─ [Group] Ignore if both lists empty (return)
    │
    ├─ YouTube URLs → _download_and_send() (no typing wrapper)
    │   ├─ Fetch metadata silently (no typing indicator)
    │   ├─ Check filesize/filesize_approx vs MAX_FILE_SIZE
    │   ├─ If >50MB → skip silently (log youtube_skipped_large)
    │   └─ If ≤50MB → download_video() → reply_video()
    │
    ├─ Non-YouTube supported URLs → typing_indicator wraps:
    │   ├─ @with_request_logging (decorator)
    │   │   │
    │   │   ├─ log_request_received() → logs "request_received" event
    │   │   │
    │   │   ▼
    │   │   handlers._download_and_send()
    │   │       │
    │   │       ├─ platforms.detect_platform(url) → "tiktok"/"instagram"
    │   │       │
    │   │       ├─ [Instagram] → platforms.instagram.handle_instagram()
    │   │       │   ├─ If metadata fails → gallery-dl with cookies
    │   │       │   └─ If metadata succeeds → download_images()
    │   │       │
    │   │       ├─ [TikTok] → platforms.tiktok.handle_tiktok()
    │   │       │   ├─ Try video download
    │   │       │   └─ If fails → gallery-dl for photo posts
    │   │       │
    │   │       └─ cleanup temp files
    │   │       │
    │   │       ▼
    │   │   @with_request_logging (decorator)
    │   │       │
    │   │       ├─ log_request_completed() → logs "request_completed" event
    │   │       │
    │   │       ▼
    │   │   Done
    │   │
    │   └─ Cancel typing indicator
    │
    ├─ Unsupported URLs → handle_gallery_dl_fallback()
    │   ├─ Set platform from URL domain (for logging)
    │   ├─ Try download_gallery_dl_images() → send_images()
    │   ├─ Try download_gallery_dl_video() → reply_video()
    │   ├─ If nothing works:
    │   │   ├─ [Group] silently return (no message)
    │   │   └─ [P2P] show "Unsupported platform" error
    │   └─ cleanup temp dirs
    │
    └─ Cancel typing indicator
```

## External Dependencies

- **yt-dlp** - Installed as system binary. Called via subprocess.
- **gallery-dl** - Installed as system binary. Called via subprocess for: Instagram image downloads (with cookies), TikTok photo posts (no cookies), and unsupported platform fallback (best-effort for 100+ services).
- **ffmpeg** - Required for audio extraction (MP3 conversion). Installed in Docker image.
- **python-telegram-bot** - Telegram Bot API wrapper. Installed via pip.
- **python-dotenv** - .env file loading.

## Structured Logging

Logs are written in JSON format for easy querying with `jq` and log aggregators. Three separate files route logs by type using `logging.Filter` subclasses.

### Log Files

| File | Logger | Contains |
|------|--------|----------|
| `requests.jsonl` | `media_downloader.requests` | Request lifecycle: received, completed, failed |
| `request-details.jsonl` | `media_downloader.details` | Intermediate steps: yt-dlp calls, retries, gallery-dl |
| `service.jsonl` | `media_downloader.service` | Bot events: start/stop, chat membership, new users |

Append `.dev.jsonl` for MODE=development (e.g. `requests.dev.jsonl`).

### Log Schema

Request received (in `requests.jsonl`):
```json
{
  "timestamp": "2026-06-01T16:16:36.527047+03:00",
  "level": "INFO",
  "message": "Request received",
  "event": "request_received",
  "request_id": "3df4888f",
  "url": "https://youtube.com/watch?v=abc",
  "user": {"id": 123, "name": "John", "username": "john"},
  "chat": {"id": -100, "name": "Group", "type": "group"}
}
```

Request completed (in `requests.jsonl`):
```json
{
  "timestamp": "2026-06-01T16:16:39.195279+03:00",
  "level": "INFO",
  "message": "Request completed",
  "event": "request_completed",
  "request_id": "3df4888f",
  "url": "https://youtube.com/watch?v=abc",
  "platform": "youtube",
  "duration_ms": 2668,
  "success": true,
  "content_type": "video",
  "file_size_mb": 45.2,
  "user": {"id": 123, "name": "John", "username": "john"},
  "chat": {"id": -100, "name": "Group", "type": "group"}
}
```

Reply-to-retry uses `"event": "reply_to_retry"` and `"message": "Reply to retry received/completed"`.

Service event (in `service.jsonl`):
```json
{
  "timestamp": "2026-06-01T16:16:36.527047+03:00",
  "level": "INFO",
  "message": "Bot added to chat",
  "event": "bot_added_to_chat",
  "chat": {"id": -100789, "name": "Test Group", "type": "supergroup"},
  "added_by": {"id": 123456, "name": "Admin", "username": "admin"}
}
```

Service events: `bot_started`, `bot_stopped`, `new_user_started`, `bot_added_to_chat`, `bot_rejected_group_addition`, `bot_removed_from_chat`, `bot_added_as_admin`, `bot_admin_rights_changed`, `bot_removed_as_admin`, `user_blocked_bot`, `unauthorized_access`.

Detail log (in `request-details.jsonl`):
```json
{
  "timestamp": "2026-06-01T16:16:37.123456+03:00",
  "level": "INFO",
  "message": "download_video: running yt-dlp",
  "url": "https://youtube.com/watch?v=abc",
  "request_id": "3df4888f",
  "platform": "youtube"
}
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `development` | `development`/`dev` or `production`/`prod`. Determines log file name. |
| `LOG_OUTPUT` | `both` | `console` (or `stdout`), `file`, or `both`. Controls output destinations. |
| `LOG_DIR` | `logs` | Directory for log files |

### File Rotation

- `logs/requests.dev.jsonl` / `logs/requests.jsonl` - Request lifecycle (10MB, 5 backups)
- `logs/request-details.dev.jsonl` / `logs/request-details.jsonl` - Download steps (10MB, 5 backups)
- `logs/service.dev.jsonl` / `logs/service.jsonl` - Bot events (10MB, 5 backups)

### Example Queries

```bash
# All YouTube requests
cat logs/requests.jsonl | jq 'select(.platform == "youtube")'

# Failed requests
cat logs/requests.jsonl | jq 'select(.event == "request_failed")'

# Slow downloads (>5 seconds)
cat logs/requests.jsonl | jq 'select(.event == "request_completed" and .duration_ms > 5000)'

# Request lifecycle for a specific request_id (across both files)
cat logs/requests.jsonl | jq 'select(.request_id == "3df4888f")'
cat logs/request-details.jsonl | jq 'select(.request_id == "3df4888f")'

# Reply-to-retry requests
cat logs/requests.jsonl | jq 'select(.event == "reply_to_retry")'

# Bot startup events
cat logs/service.jsonl | jq 'select(.event == "bot_started" or .message == "Bot started")'

# All chat membership changes
cat logs/service.jsonl | jq 'select(.event | test("bot_added_to_chat|bot_removed_from_chat|bot_status_changed"))'

# User blocks bot
cat logs/service.jsonl | jq 'select(.event == "user_blocked_bot")'

# Admin rights changes
cat logs/service.jsonl | jq 'select(.event | test("bot_added_as_admin|bot_admin_rights_changed|bot_removed_as_admin"))'

# Bot added as admin to channel
cat logs/service.jsonl | jq 'select(.event == "bot_added_as_admin" and .chat.type == "channel")'

# Unauthorized access attempts
cat logs/service.jsonl | jq 'select(.event == "unauthorized_access")'

# Non-admin group additions rejected
cat logs/service.jsonl | jq 'select(.event == "bot_rejected_group_addition")'
```

## Why Subprocess (not Python import)?

- yt-dlp can be upgraded independently (`pip install -U yt-dlp`)
- No version coupling between bot code and yt-dlp
- Easier to debug (can run yt-dlp commands manually)
- Matches how all successful yt-dlp wrappers work (Seal, VidBee, etc.)

## Deployment

**Image:** Multi-stage build — build stage compiles Python deps, runtime stage is Python 3.12-slim with yt-dlp, gallery-dl, and ffmpeg.

**Container:**
- Runs as non-root `appuser`
- `restart: unless-stopped` — survives reboots
- Env vars loaded from `.env` file
- Logs written to a bind-mounted `logs/` directory

**Volumes:**
- `./logs:/usr/src/app/logs` — persistent structured JSON logs
- `./cookies.txt:/usr/src/app/cookies.txt:ro` — Instagram browser cookies (read-only)
- `./allowed-contacts.json:/usr/src/app/allowed-contacts.json:ro` — user allowlist (read-only)
- `bot-downloads:/tmp/bot-downloads` — temp download directory (named volume)

**Deploying updates:**
```bash
./compose.sh  # Rebuilds image (no cache) and restarts container
```

**Useful commands:**
```bash
docker compose logs -f           # Watch live logs
docker compose down              # Stop and remove
docker compose down -v           # Stop, remove, delete volumes
docker compose exec bot bash     # Shell into running container
```

For detailed deployment notes (hostnames, paths, secrets), see `docs/deployment-private.md` (gitignored).

## Development Workflow

Two separate bot instances run in parallel for development and production:

| | Dev Bot | Prod Bot |
|---|---|---|
| **Bot** | `@mememediasavertestbot` | `@mememediasaverbot` |
| **Runs on** | Local machine (Docker) | Orange Pi 3B |
| **Code** | Latest local `main` | Latest `origin/main` |
| **Log file** | `requests.dev.jsonl` (MODE=development) | `requests.jsonl` (MODE=production) |

Both bots share the same group chats and test topics. This lets you test changes locally before pushing to production — send the same URL to both bots and compare behavior.

**Typical workflow:**
1. Make changes locally, run `python -m pytest tests/ -v`
2. Rebuild dev bot: `docker compose up -d --build`
3. Test in shared group — both bots receive the same messages
4. If dev bot works correctly, push and deploy to prod
