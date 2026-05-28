# Architecture

## Overview

Modular design. Each module has one clear responsibility. yt-dlp is called as a subprocess, not imported as a library.

## Modules

### config.py
Loads settings from `.env` via python-dotenv. Exports constants:
- `BOT_TOKEN` - Telegram bot token
- `ALLOWED_USER_IDS` - Comma-separated user IDs (empty = allow all)
- `DOWNLOAD_DIR` - Temp directory for downloads (default: /tmp/bot-downloads)
- `MAX_FILE_SIZE` - Max download size in MB (default: 50)
- `MAX_CONCURRENT_DOWNLOADS` - Concurrency limit (default: 3)
- `LOG_OUTPUT` - Logging destination: "stdout" (dev) or "file" (prod)
- `LOG_DIR` - Log file directory (default: logs)

### utils.py
Pure utility functions, no dependencies:
- `detect_platform(url)` - Returns "youtube", "tiktok", "instagram", or None
- `is_valid_url(text)` - Checks for HTTP(S) URL pattern
- `extract_urls(text)` - Finds all URLs in text
- `cleanup_file(path)` / `cleanup_dir(path)` - Safe file removal

### downloader.py
Wraps yt-dlp binary calls via subprocess:
- `get_metadata(url)` - Runs `yt-dlp --dump-json`, returns dict with title/thumbnail/duration
- `download_video(url, path, max_size, platform)` - Downloads video, retries with lower quality on failure
- `download_audio(url, path)` - Extracts audio as MP3
- `download_images(url, dir)` - Downloads carousel/gallery images

### handlers.py
Telegram message handlers:
- `start_command` - Welcome message
- `help_command` - Platform list and usage
- `audio_command` - Download as MP3
- `handle_url` - Main handler: detects URL, fetches metadata, downloads, sends to Telegram

### logging_config.py
Structured JSON logging with zero external dependencies:
- `JSONFormatter` - Custom `logging.Formatter` that outputs JSON with timestamp, level, message, and extra fields
- `setup_logging()` - Configures logging based on `LOG_OUTPUT` env var
  - stdout mode: StreamHandler for development
  - file mode: RotatingFileHandler for `requests.jsonl` (all levels) and `errors.jsonl` (ERROR+), plus stderr for errors
- `log_request()` - Logs media requests with user, chat, and media metadata
- `log_error()` - Logs download failures with error context

### inline.py
Inline query handler:
- `inline_query` - Handles `@botname <url>` in any chat
- Returns InlineQueryResultArticle with title and thumbnail

### bot.py
Entry point:
- Creates `Application` with bot token
- Registers all handlers
- Starts polling

## Data Flow

```
User sends URL
    │
    ▼
handlers.handle_url()
    │
    ├─ utils.detect_platform(url) → "youtube"
    ├─ downloader.get_metadata(url) → {title, thumbnail, ...}
    ├─ downloader.download_video(url, path) → True
    ├─ logging_config.log_request() → structured JSON log
    └─ send file to Telegram, cleanup temp files

On error:
    ├─ logging_config.log_error() → error JSON log
    └─ notify user of failure
```

## External Dependencies

- **yt-dlp** - Installed as system binary. Called via subprocess.
- **python-telegram-bot** - Telegram Bot API wrapper. Installed via pip.
- **python-dotenv** - .env file loading.

## Structured Logging

Logs are written in JSON format for easy querying with `jq` and log aggregators.

### Log Schema

Request log entry:
```json
{
  "timestamp": "2026-05-28T14:32:01.123Z",
  "level": "INFO",
  "event": "media_request",
  "url": "https://youtube.com/watch?v=abc",
  "platform": "youtube",
  "content_type": "video",
  "user": {"id": 123, "name": "John", "username": "john"},
  "chat": {"id": -100, "name": "Group", "type": "group"},
  "media": {"duration_seconds": 120, "file_size_mb": 45.2, "image_count": null, "quality": "720p"}
}
```

Error log entry:
```json
{
  "timestamp": "2026-05-28T14:32:05.456Z",
  "level": "ERROR",
  "event": "download_failed",
  "url": "https://...",
  "error": "yt-dlp timeout",
  "platform": "youtube",
  "user": {"id": 123, "name": "John", "username": "john"},
  "chat": {"id": -100, "name": "Group", "type": "group"}
}
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_OUTPUT` | `stdout` | `stdout` for dev, `file` for production |
| `LOG_DIR` | `logs` | Directory for log files |

### File Rotation (Production)

- `logs/requests.jsonl` - All media request logs (10MB, 5 backups)
- `logs/errors.jsonl` - Error logs only (10MB, 5 backups)

### Example Queries

```bash
# All YouTube requests
cat logs/requests.jsonl | jq 'select(.platform == "youtube")'

# Large video downloads (>100MB)
cat logs/requests.jsonl | jq 'select(.media.file_size_mb > 100)'

# Error summary
cat logs/errors.jsonl | jq -r '.error' | sort | uniq -c | sort -rn
```

## Why Subprocess (not Python import)?

- yt-dlp can be upgraded independently (`pip install -U yt-dlp`)
- No version coupling between bot code and yt-dlp
- Easier to debug (can run yt-dlp commands manually)
- Matches how all successful yt-dlp wrappers work (Seal, VidBee, etc.)
