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

### utils.py
Pure utility functions, no dependencies:
- `detect_platform(url)` - Returns "youtube", "tiktok", "instagram", or None (supports youtube.com, youtu.be, music.youtube.com)
- `is_valid_url(text)` - Checks for HTTP(S) URL pattern
- `extract_urls(text)` - Finds all URLs in text
- `cleanup_file(path)` / `cleanup_dir(path)` - Safe file removal

### downloader.py
Wraps yt-dlp and gallery-dl binary calls via subprocess:
- `_find_ytdlp()` / `_find_gallery_dl()` - Locate binaries (checks PATH, then venv bin/ for VS Code compatibility)
- `get_metadata(url)` - Runs `yt-dlp --dump-json`, returns dict with title/thumbnail/duration
- `download_video(url, path, max_size, platform)` - Downloads video, retries with lower quality on failure. Logs start/success/failure.
- `download_audio(url, path)` - Extracts audio as MP3. Logs start/success/failure.
- `download_images(url, dir)` - Downloads carousel/gallery images via gallery-dl (with cookies), falls back to yt-dlp thumbnail extraction
- `download_instagram_gallery_dl(url, dir, cookies)` - Downloads Instagram images using gallery-dl with browser-exported cookies for authentication

### handlers.py
Telegram message handlers with group detection:
- `is_group_chat(update)` - Checks if message is from group/supergroup
- `_is_allowed_group(chat_id)` - Checks if group is in allowlist
- `start_command` - Welcome message
- `help_command` - Platform list and usage
- `audio_command` - Download as MP3 (registered as CommandHandler, sets platform/success metadata for logging)
- `handle_url` - Main handler: detects group/P2P, filters URLs, downloads, sends to Telegram
  - In groups: silently ignores unsupported URLs, processes supported ones
  - In P2P: shows error messages for invalid/unsupported URLs
  - Respects ALLOWED_GROUP_IDS config
- `ytmusic_callback` - Handles YouTube Music format picker (Audio/Video/Both)
  - "Both" downloads video+audio concurrently via `asyncio.to_thread()` + `asyncio.gather()`
  - Sends video first, then audio with minimal gap
  - All branches have structured logging (`_log.info`/`_log.warning`)
  - `content_type` metadata set to "both" for combined downloads

### logging_config.py
Structured JSON logging with zero external dependencies:
- `JSONFormatter` - Custom `logging.Formatter` that outputs JSON with timestamp (Europe/Kyiv timezone, UTC+2/+3), level, message, and extra fields (with `ensure_ascii=False` for Unicode support)
- `_resolve_log_file(mode)` - Maps MODE to log filename: dev/development → `requests.dev.jsonl`, production → `requests.jsonl`
- `setup_logging()` - Configures logging based on `MODE` and `LOG_OUTPUT` env vars
  - `LOG_OUTPUT=console` (or "stdout"): StreamHandler only
  - `LOG_OUTPUT=file`: RotatingFileHandler only (10MB, 5 backups)
  - `LOG_OUTPUT=both` (default): Both console and file handlers
  - File name determined by MODE: dev → `requests.dev.jsonl`, prod → `requests.jsonl`
- `with_request_logging()` - Decorator that wraps handlers and logs request lifecycle:
  - `request_received` when handler starts
  - `request_completed` when handler finishes (success or expected failure)
  - `request_failed` when handler throws exception
- `log_request_received()` - Logs when a request is received
- `log_request_completed()` - Logs when a request completes
- `log_request_failed()` - Logs when a request fails with an exception

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
    │   (logged via @with_request_logging on handle_url + _log calls in audio_command)
    │
    ├─ is_group_chat() → true/false
    │
    ├─ [Group] Filter to supported URLs only
    │   ├─ No supported URLs → silently ignore (return)
    │   └─ Has supported URLs → continue
    │
    ├─ [P2P] Show error if no valid URLs
    │
    ├─ _is_allowed_group() → check allowlist (groups only)
    │
    ├─ Start typing indicator
    │
    ├─ @with_request_logging (decorator)
    │   │
    │   ├─ log_request_received() → logs "request_received" event
    │   │
    │   ▼
    │   handlers._download_and_send()
    │       │
    │       ├─ utils.detect_platform(url) → "youtube"
    │       ├─ downloader.get_metadata(url) → {title, thumbnail, ...}
    │       │
    │       ├─ [Instagram] If metadata fails → download_instagram_gallery_dl() via gallery-dl
    │       │
    │       ├─ [YouTube Music] If music.youtube.com → show format picker (Audio/Video/Both)
    │       │   "Both" → asyncio.gather(download_video, download_audio) → send video → send audio
    │       │   Otherwise → download_video() → reply_video()
    │       │
    │       └─ cleanup temp files
    │       │
    │       ▼
    │   @with_request_logging (decorator)
    │       │
    │       ├─ log_request_completed() → logs "request_completed" event (success)
    │       │
    │       ▼
    │   Done
    │
    └─ Cancel typing indicator
```

## External Dependencies

- **yt-dlp** - Installed as system binary. Called via subprocess.
- **gallery-dl** - Installed as system binary. Called via subprocess for Instagram image downloads with cookies authentication.
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
