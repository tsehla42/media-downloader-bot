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
    └─ send file to Telegram, cleanup temp files
```

## External Dependencies

- **yt-dlp** - Installed as system binary. Called via subprocess.
- **python-telegram-bot** - Telegram Bot API wrapper. Installed via pip.
- **python-dotenv** - .env file loading.

## Why Subprocess (not Python import)?

- yt-dlp can be upgraded independently (`pip install -U yt-dlp`)
- No version coupling between bot code and yt-dlp
- Easier to debug (can run yt-dlp commands manually)
- Matches how all successful yt-dlp wrappers work (Seal, VidBee, etc.)
