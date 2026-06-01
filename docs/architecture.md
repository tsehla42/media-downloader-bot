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
- `LOG_OUTPUT` - Logging destination: "stdout" (dev) or "file" (prod)
- `LOG_DIR` - Log file directory (default: logs)

### utils.py
Pure utility functions, no dependencies:
- `detect_platform(url)` - Returns "youtube", "tiktok", "instagram", or None (supports youtube.com, youtu.be, music.youtube.com)
- `is_valid_url(text)` - Checks for HTTP(S) URL pattern
- `extract_urls(text)` - Finds all URLs in text
- `cleanup_file(path)` / `cleanup_dir(path)` - Safe file removal

### downloader.py
Wraps yt-dlp and gallery-dl binary calls via subprocess. Uses instaloader as last-resort Instagram fallback:
- `_find_ytdlp()` / `_find_gallery_dl()` - Locate binaries (checks PATH, then venv bin/ for VS Code compatibility)
- `get_metadata(url)` - Runs `yt-dlp --dump-json`, returns dict with title/thumbnail/duration
- `download_video(url, path, max_size, platform)` - Downloads video, retries with lower quality on failure
- `download_audio(url, path)` - Extracts audio as MP3
- `download_images(url, dir)` - Downloads carousel/gallery images via gallery-dl (with cookies), falls back to yt-dlp thumbnail extraction
- `download_instagram_gallery_dl(url, dir, cookies)` - Downloads Instagram images using gallery-dl with browser-exported cookies for authentication
- `download_instagram_image(url, path)` - Last-resort fallback: uses instaloader to download single images (no auth, often gets 403)

### handlers.py
Telegram message handlers with group detection:
- `is_group_chat(update)` - Checks if message is from group/supergroup
- `_is_allowed_group(chat_id)` - Checks if group is in allowlist
- `start_command` - Welcome message
- `help_command` - Platform list and usage
- `audio_command` - Download as MP3
- `handle_url` - Main handler: detects group/P2P, filters URLs, downloads, sends to Telegram
  - In groups: silently ignores unsupported URLs, processes supported ones
  - In P2P: shows error messages for invalid/unsupported URLs
  - Respects ALLOWED_GROUP_IDS config
- YouTube Music URLs (music.youtube.com) automatically sent as audio

### logging_config.py
Structured JSON logging with zero external dependencies:
- `JSONFormatter` - Custom `logging.Formatter` that outputs JSON with timestamp, level, message, and extra fields (with `ensure_ascii=False` for Unicode support)
- `setup_logging()` - Configures logging based on `LOG_OUTPUT` env var
  - stdout mode: StreamHandler for development
  - file mode: RotatingFileHandler for `requests.jsonl` (all levels), plus stderr for errors
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
User sends URL
    │
    ▼
handlers.handle_url()
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
    │       │   If gallery-dl fails → download_instagram_image() via instaloader (fallback)
    │       │
    │       ├─ [YouTube Music] If music.youtube.com → download_audio() → reply_audio()
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
- **instaloader** - Python library. Last-resort Instagram fallback (no auth, often gets 403 from Instagram's GraphQL API).
- **python-telegram-bot** - Telegram Bot API wrapper. Installed via pip.
- **python-dotenv** - .env file loading.

## Structured Logging

Logs are written in JSON format for easy querying with `jq` and log aggregators. All events go to a single `requests.jsonl` file.

### Log Schema

Request received:
```json
{
  "timestamp": "2026-05-30T13:16:36.527047+00:00",
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
  "timestamp": "2026-05-30T13:16:39.195279+00:00",
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
  "timestamp": "2026-05-30T13:16:35.123456+00:00",
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
| `LOG_OUTPUT` | `stdout` | `stdout` for dev, `file` for production |
| `LOG_DIR` | `logs` | Directory for log files |

### File Rotation (Production)

- `logs/requests.jsonl` - All request lifecycle events (10MB, 5 backups)
- `logs/errors.jsonl` - Error logs only (10MB, 5 backups)

### Example Queries

```bash
# All YouTube requests
cat logs/requests.jsonl | jq 'select(.platform == "youtube")'

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
