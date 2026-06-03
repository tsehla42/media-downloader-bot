# Architecture

## Overview

Modular design. Each module has one clear responsibility. yt-dlp is called as a subprocess, not imported as a library.

## Modules

### config.py
Loads settings from `.env` via python-dotenv. Exports constants:
- `BOT_TOKEN` - Telegram bot token
- `ALLOWED_USER_IDS` - Comma-separated user IDs (empty = allow all)
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
- `is_authorized(update)` - Checks if request is authorized (groups checked against ALLOWED_GROUP_IDS, DMs against ALLOWED_USER_IDS)
- `is_group_chat(update)` - Checks if message is from group/supergroup
- `_is_allowed(user_id)` - Checks if user is in allowlist (empty = allow all)
- `_is_allowed_group(chat_id)` - Checks if group is in allowlist (empty = allow all)

### commands.py
User-facing commands, depends on auth, config, logging_config:
- `_user_caption_prefs` - Per-user caption preferences dict (user_id -> bool)
- `get_caption_for_user(user_id, title)` - Returns caption string based on preference (empty if disabled)
- `start_command(update, context)` - Welcome message, logs new users
- `help_command(update, context)` - Supported platforms and commands list
- `caption_command(update, context)` - Toggle video captions on/off

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
- `handle_tiktok(update, context, url)` - Tries video download, falls back to gallery-dl for photo posts

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

### handlers.py
Thin orchestrator, depends on auth, commands, platforms, telegram_utils, downloader:
- `my_chat_member_handler(update, context)` - Handles bot membership changes (added, removed, promoted, demoted)
- `audio_command(update, context)` - Download as MP3 (registered as CommandHandler)
- `_download_and_send(update, context, url, silent, reply_to_message_id)` - Orchestrates download with YouTube size check and error suppression
- `handle_reply_to_url(update, context)` - Retries download when user replies to message with URL and mentions bot
- `handle_url(update, context)` - Main handler: detects group/P2P, filters URLs, handles YouTube/other typing separately

### logging_config.py
Structured JSON logging with zero external dependencies:
- `JSONFormatter` - Custom `logging.Formatter` that outputs JSON with timestamp (Europe/Kyiv timezone)
- `_resolve_log_file(mode)` - Maps MODE to log filename
- `setup_logging()` - Configures logging based on `MODE` and `LOG_OUTPUT` env vars
- `with_request_logging()` - Decorator that wraps handlers and logs request lifecycle
- `log_request_received()` / `log_request_completed()` / `log_request_failed()` - Log request events

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
    ├─ Reply with bot mention? → handle_reply_to_url()
    │   └─ Extract URL from replied message → _download_and_send(silent=False)
    │
    ├─ is_group_chat() → true/false
    │
    ├─ [Group] Filter to supported URLs only
    │   ├─ No supported URLs → silently ignore (return)
    │   └─ Has supported URLs → continue
    │
    ├─ [P2P] Show error if no valid URLs
    │
    ├─ Split YouTube vs non-YouTube URLs
    │
    ├─ YouTube URLs → _download_and_send() (no typing wrapper)
    │   ├─ Fetch metadata silently (no typing indicator)
    │   ├─ Check filesize/filesize_approx vs MAX_FILE_SIZE
    │   ├─ If >50MB → skip silently (log youtube_skipped_large)
    │   └─ If ≤50MB → download_video() → reply_video()
    │
    ├─ Non-YouTube URLs → typing_indicator wraps:
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
    └─ Cancel typing indicator
```

## External Dependencies

- **yt-dlp** - Installed as system binary. Called via subprocess.
- **gallery-dl** - Installed as system binary. Called via subprocess for Instagram image downloads (with cookies) and TikTok photo posts (no cookies needed).
- **ffmpeg** - Required for audio extraction (MP3 conversion). Installed in Docker image.
- **python-telegram-bot** - Telegram Bot API wrapper. Installed via pip.
- **python-dotenv** - .env file loading.

## Structured Logging

Logs are written in JSON format for easy querying with `jq` and log aggregators. The log file name depends on MODE: `requests.dev.jsonl` for development, `requests.jsonl` for production.

### Log Schema

Request received:
```json
{
  "timestamp": "2026-06-01T16:16:36.527047+03:00",
  "level": "INFO",
  "message": "Request received",
  "event": "request_received",
  "request_id": "3df4888f",
  "url": "https://youtube.com/watch?v=abc",
  "platform": "youtube",
  "user": {"id": 123, "name": "John", "username": "john"},
  "chat": {"id": -100, "name": "Group", "type": "group"}
}
```

Request completed:
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
  "file_size_mb": 45.2
}
```

Request failed:
```json
{
  "timestamp": "2026-06-01T16:16:35.123456+03:00",
  "level": "ERROR",
  "message": "Request failed: yt-dlp timeout",
  "event": "request_failed",
  "request_id": "a1b2c3d4",
  "url": "https://youtube.com/watch?v=abc",
  "platform": "youtube",
  "error": "yt-dlp timeout",
  "error_type": "TimeoutError"
}
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `development` | `development`/`dev` or `production`/`prod`. Determines log file name. |
| `LOG_OUTPUT` | `both` | `console` (or `stdout`), `file`, or `both`. Controls output destinations. |
| `LOG_DIR` | `logs` | Directory for log files |

### File Rotation

- `logs/requests.dev.jsonl` - Development mode (10MB, 5 backups)
- `logs/requests.jsonl` - Production mode (10MB, 5 backups)

### Example Queries

```bash
# All YouTube requests (adjust file name based on MODE)
cat logs/requests.jsonl | jq 'select(.platform == "youtube")'
cat logs/requests.dev.jsonl | jq 'select(.platform == "youtube")'

# Failed requests
cat logs/requests.jsonl | jq 'select(.event == "request_failed")'

# Slow downloads (>5 seconds)
cat logs/requests.jsonl | jq 'select(.event == "request_completed" and .duration_ms > 5000)'

# Request lifecycle for a specific request_id
cat logs/requests.jsonl | jq 'select(.request_id == "3df4888f")'
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
- `./cookies.txt:/app/cookies.txt:ro` — Instagram browser cookies (read-only)
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
