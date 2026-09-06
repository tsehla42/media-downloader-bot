# Media Downloader Bot

## Overview

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram. Users paste a URL, get the media back. Also silently attempts gallery-dl for 100+ other services (Pinterest, Pixiv, X, Reddit, DeviantArt, etc.) -- works as a best-effort fallback.

Modular design. Each module has one clear responsibility. yt-dlp is called as a subprocess, not imported as a library.

## Documentation

- [Group Chats](group-chats/) - How bot works in groups
- [Guest Mode](guest-mode/) - Bot API 10.0 guest mode
- [P2P Chats](p2p-chats/) - Private chat behavior
- [Logging](logs/) - Logging system
- [Content Delivery](content-delivery/) - Media downloading
- [Media Cache](cache/) - SQLite cache for guest mode file_ids
- [Cookies](cookies.md) - Instagram cookie refresh setup
- [Deploy Guide](deploy.md) - Production server deployment flow (gitignored)

## Modules

### config.py
Loads settings from `.env` via python-dotenv. Exports constants:
- `BOT_TOKEN` - Telegram bot token
- `BOT_ADMIN_IDS` - Comma-separated admin user IDs (empty = anyone can add bot to groups)
- `ALLOWED_USER_IDS` - Merged from `allowed-users.json` (array of objects with `id` field) + env var. Empty sources = allow all; configured sources = user must be in list.
- `ALLOWED_IDS_CONFIGURED` - Boolean: True if any ID source (JSON file or env var) exists
- `ALLOWED_GROUP_IDS` - Comma-separated group chat IDs (empty = allow all groups)
- `DOWNLOAD_DIR` - Temp directory for downloads (default: /tmp/bot-downloads)
- `MAX_FILE_SIZE` - Max download size in MB (default: 50)
- `MAX_CONCURRENT_DOWNLOADS` - Concurrency limit (default: 3)
- `IG_USERNAME` - Instagram account username for cookie refresh via instagrapi
- `IG_PASSWORD` - Instagram account password for cookie refresh via instagrapi
- `IG_COOKIES_PATH` - Path to Netscape cookies.txt for gallery-dl Instagram auth (default: ig-cookies.txt)
- `IG_SESSION_PATH` - Path to instagrapi session JSON (default: ig-session.json)
- `TIKTOK_COOKIES_PATH` - Path to Netscape cookies.txt for TikTok auth (default: tiktok-cookies.txt)
- `GUEST_MODE_ENABLED` - Enable Bot API 10.0 guest mode (default: false)
- `STORAGE_CHANNEL_ID` - Private channel ID for guest mode file storage (bot must be admin). Files uploaded here to get `file_id`s for InlineQueryResult.
- `MODE` - Environment mode: "development" (default) or "production". Determines log file name.
- `LOG_OUTPUT` - Logging destination: "console", "file", or "both" (default). "stdout" is an alias for "console".
- `LOG_DIR` - Log file directory (default: logs)
- `LOG_LEVEL` - Logging level: "DEBUG", "INFO" (default), "WARNING", "ERROR", "CRITICAL"

### auth.py
Authorization checks, depends on config:
- `is_authorized(update)` - Groups: always allowed (bot only exists if admin added it). P2P: checks ALLOWED_USER_IDS (empty sources = allow all; configured sources = user must be in list).
- `is_bot_admin(user_id)` - Checks if user is in BOT_ADMIN_IDS (empty = allow all)
- `was_notified(user_id)` - Checks if user has been told they're not authorized (P2P, in-memory set)
- `mark_notified(user_id)` - Marks user as notified (resets on restart)
- `was_notified_guest(user_id)` - Checks if user has been told they're not authorized (guest mode, separate set)
- `mark_notified_guest(user_id)` - Marks guest user as notified (resets on restart)
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
- `extract_domain(url)` - Extracts normalized domain from URL (no www., lowercase)

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
- `get_gallery_dl_domains()` - Returns frozenset of gallery-dl supported domains. Auto-generates `src/gallery_dl_domains.py` from Codeberg if missing.

### cookies.py
Instagram cookie refresh via instagrapi:
- `check_cookies_staleness(cookies_path, max_age_days=3)` - Returns True if cookies file is missing or older than threshold
- `refresh_instagram_cookies(username, password, session_path, cookies_path, max_age_days=3, force=False)` - Refreshes cookies if stale. Returns True if fresh or successfully refreshed. Preserves existing cookies on failure.
- `_login_with_session(cl, username, password, session_path)` - Tries saved session first, falls back to fresh login
- `_export_cookies_to_netscape(cookie_jar, output_path, domain)` - Converts RequestsCookieJar to Netscape format (unused — cookies exported directly from authorization_data)

### downloader.py
Wraps yt-dlp and gallery-dl binary calls via subprocess:
- `_find_ytdlp()` / `_find_gallery_dl()` - Locate binaries
- `get_metadata(url, format_selector=None, referer="", cookies="")` - Runs `yt-dlp --dump-json --no-playlist` (60s timeout). Optional `format_selector` param passes `-f` flag for accurate size estimates (used for YouTube where `download_video()` forces MP4). Optional `referer` and `cookies` params for platform-specific auth. Logs stderr on failure. Raises `DownloadAuthRequired` for age-restricted content.
- `download_video(url, path, max_size, platform)` - Downloads video, retries with lower quality on failure. When `platform="tiktok"`, adds referer header and cookies.
- `download_audio(url, path)` - Extracts audio as MP3
- `download_images(url, dir)` - Downloads carousel/gallery images via gallery-dl
- `download_gallery_dl_images(url, dir, cookies)` - Downloads images using gallery-dl
- `download_gallery_dl_video(url, dir)` - Downloads video using gallery-dl (for unsupported platform fallback)

### handlers.py
Thin orchestrator, depends on auth, commands, platforms, telegram_utils, downloader, logging_config:
- `my_chat_member_handler(update, context)` - Handles bot membership changes. When bot added to group: checks `is_bot_admin(from_user.id)` -> admin: log + allow; non-admin: `log_bot_rejected_group_addition` + reject message + leave. Also handles removed/promoted/demoted/blocked events.
- `audio_command(update, context)` - Download as MP3 (uses notification tracking for unauthorized users)
- `_download_and_send(update, context, url, silent, reply_to_message_id)` - Orchestrates download with YouTube size check, error suppression, and `skip_reason` tracking (`unsupported`, `size_limit`, `auth_required`, `metadata_failed`, `fetch_failed`, `download_failed`)
- `handle_gallery_dl_fallback(update, context, url)` - Tries gallery-dl for unsupported platforms (images then video), silent on failure
- `handle_url(update, context)` - Main handler: clears stale `_platform`, filters pure playlist URLs, authorization check, detects group/P2P, unauthorized reply-to-bot check in groups (silently ignores), splits supported/unsupported URLs, filters unsupported against gallery-dl domain whitelist, handles reply-to-retry, routes remaining unsupported URLs to gallery-dl fallback

### guest.py
Bot API 10.0 guest mode handler, depends on auth, config, downloader, platforms, utils, logging_config, httpx, cache:
- `handle_guest(update, context)` - Main handler for `guest_message` updates. Identifies caller via `guest_msg.from_user` (Telegram sends `from`, ptb maps to `from_user`). Auth check via `is_user_allowed()`. Unauthorized users get "You are not authorized" once via `answer_guest_query`, then silently ignored (uses `was_notified_guest()`/`mark_notified_guest()`). Logs unauthorized access to service.jsonl. Reply to bot message without URL is silently ignored. Reply to bot message with no text shows media type (e.g. `[photo]`) in logs. Extracts URLs from tag text OR replied-to message. Platform set from `extract_domain(url)` when `detect_platform()` returns None (for gallery-dl supported sites). Routes to download pipeline.
- `_safe_answer_guest_query(bot, guest_query_id, result)` - Wrapper around `answer_guest_query()` that catches `BadRequest` when user deletes their message before bot answers. Logs gracefully instead of throwing unhandled exception.
- `_download_and_build_result(url, platform)` - Checks cache first (via `cache.get_cached()`). On cache hit, returns cached `file_id` instantly. On miss, routes to platform-specific download: YouTube, TikTok, Instagram, or gallery-dl fallback. For TikTok, fetches metadata before download to get video ID for short URL deduplication. Stores result in cache after successful download.
- `_download_youtube(url)` - Downloads YouTube video, uploads to storage channel, returns `_video_result()`
- `_download_media_result(url, platform)` - Downloads TikTok/Instagram content (video -> gallery-dl images -> gallery-dl video). For TikTok, passes `platform="tiktok"` to `download_video()` for referer+cookies, and passes cookies+referer to `get_metadata()`.
- `_gallery_dl_result(url)` - gallery-dl fallback for unsupported platforms (tries images, then video)
- `_upload_to_telegram(file_path, media_type)` - Uploads local file to storage channel via httpx, returns `file_id`. Handles Telegram's photo response as list of PhotoSize objects (returns file_id from largest size).
- `_text_result(text)` / `_video_result(file_id)` / `_photo_result(file_id)` / `_media_group_result(file_ids)` - Build InlineQueryResult as raw dicts. Uses `video_file_id`/`photo_file_id` directly (not ptb classes) to avoid placeholder URL issues. Media group returns first photo only (inline results don't support groups).

**Critical**: Guest handler must be registered BEFORE `handle_url` text handler in `bot.py`. `filters.TEXT` matches guest messages because `Update.effective_message` now includes `guest_message`.

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
- `log_guest_request_received()` / `log_guest_request_completed()` - Log guest mode request lifecycle (use `requests_logger`). Only logs when URL is present.
- `log_new_user()` / `log_bot_added_to_chat()` / `log_bot_rejected_group_addition()` / `log_bot_removed_from_chat()` / `log_admin_rights_changed()` / `log_user_blocked_bot()` / `log_unauthorized_access()` - System events (use `service_logger`)
- `_extract_admin_rights(member)` - Extracts admin rights dict from ChatMemberAdministrator

### bot.py
Entry point:
- Creates `Application` with bot token
- Registers all handlers (guest handler BEFORE text handler -- see guest.py note)
- Adds `"guest_message"` to `allowed_updates` when `GUEST_MODE_ENABLED=true`
- Starts polling via `app.run_polling()`
- Global `error_handler` for unhandled exceptions

## Data Flow

```
User sends URL or /audio command
    |
    v
handlers.handle_url()
    |
    +-- /audio -> audio_command() -> download_audio() -> reply_audio()
    |   (logged via @with_request_logging)
    |
    +-- Reply to message + bot mention? -> reply-to-retry flow
    |   +-- Extract URL from replied message -> _download_and_send(silent=False)
    |
    +-- Split URLs into supported (YT/TT/IG) and unsupported
    |
    +-- Filter: skip pure playlist URLs (list= without v=) -> skip_reason: "playlist"
    |
    +-- Filter unsupported URLs against gallery-dl domain whitelist
    |   +-- Domains not in list -> skip (log as success=false, platform=domain)
    |   +-- Domains in list -> keep for gallery-dl fallback
    |
    +-- [Group] Ignore if both lists empty (return)
    |
    +-- YouTube URLs -> _download_and_send() (no typing wrapper)
    |   +-- Fetch metadata with --no-playlist (60s timeout)
    |   +-- Age-restricted? -> skip_reason: "auth_required"
    |   +-- Check filesize/filesize_approx vs MAX_FILE_SIZE
    |   +-- If >50MB -> skip (skip_reason: "size_limit")
    |   +-- If <=50MB -> download_video() -> reply_video()
    |
    +-- Non-YouTube supported URLs -> typing_indicator wraps:
    |   +-- @with_request_logging (decorator)
    |   |   |
    |   |   +-- log_request_received() -> logs "request_received" event
    |   |   |
    |   |   v
    |   |   handlers._download_and_send()
    |   |       |
    |   |       +-- platforms.detect_platform(url) -> "tiktok"/"instagram"
    |   |       |
    |   |       +-- [Instagram] -> platforms.instagram.handle_instagram()
    |   |       |   +-- If metadata fails -> gallery-dl with cookies
    |   |       |   +-- If metadata succeeds -> download_images()
    |   |       |
    |   |       +-- [TikTok] -> platforms.tiktok.handle_tiktok()
    |   |       |   +-- Try video download
    |   |       |   +-- If fails -> gallery-dl for photo posts
    |   |       |
    |   |       +-- cleanup temp files
    |   |       |
    |   |       v
    |   |   @with_request_logging (decorator)
    |   |       |
    |   |       +-- log_request_completed() -> logs "request_completed" event
    |   |       |
    |   |       v
    |   |   Done
    |   |
    |   +-- Cancel typing indicator
    |
    +-- Unsupported URLs -> handle_gallery_dl_fallback()
    |   +-- Set platform from URL domain (for logging)
    |   +-- Try download_gallery_dl_images() -> send_images()
    |   +-- Try download_gallery_dl_video() -> reply_video()
    |   +-- If nothing works:
    |   |   +-- [Group] silently return (no message)
    |   |   +-- [P2P] show "Unsupported platform" error
    |   +-- cleanup temp dirs
    |
    +-- Cancel typing indicator

Guest mode (GUEST_MODE_ENABLED=true):
    User mentions @botname in any chat
        |
        v
    Telegram sends guest_message update
        |
        v
    guest.handle_guest()
        |
        +-- Caller: guest_msg.from_user (Telegram 'from' -> ptb from_user)
        +-- Auth: is_user_allowed(caller_id)
        |   +-- Unauthorized -> first call: answer_guest_query("You are not authorized")
        |   |   + log_unauthorized_access() -> service.jsonl
        |   |   Subsequent calls: silently ignored (via was_notified_guest())
        |   +-- Authorized -> continue
        +-- URL: extract from tag text OR replied-to message
        |
        +-- No URL -> reply to bot? -> silently ignore
        |          -> tag only? -> answer_guest_query("Please include a URL")
        |
        +-- URL found -> log_guest_request_received() -> requests.jsonl
        |   (includes user, chat, reply context)
        |
        +-- Platform detected -> _download_and_build_result(url, platform)
        |   +-- YouTube -> _download_youtube()
        |   +-- TikTok/Instagram -> _download_media_result()
        |   +-- Unknown platform, domain in gallery-dl list -> _gallery_dl_result()
        |   +-- Unknown platform, domain NOT in list -> "Unsupported platform"
        |
        +-- Download OK -> _upload_to_telegram() -> get file_id
        |   (handles Telegram photo list response)
        |   +-- answer_guest_query(InlineQueryResult with file_id)
        |   |   +-- Single photo only (inline results don't support media groups)
        |   +-- log_guest_request_completed(success=true, platform=domain) -> requests.jsonl
        |
        +-- Download failed -> answer_guest_query("Download failed: {error}")
            +-- log_guest_request_completed(success=false, error=...) -> requests.jsonl
```

## External Dependencies

- **yt-dlp** - Installed as system binary. Called via subprocess.
- **gallery-dl** - Installed as system binary. Called via subprocess for: Instagram image downloads (with cookies), TikTok photo posts (no cookies), and unsupported platform fallback (best-effort for 100+ services).
- **ffmpeg** - Required for audio extraction (MP3 conversion). Installed in Docker image.
- **deno** - JavaScript runtime for yt-dlp YouTube extraction (n-challenge solver). Installed in Docker image via multi-stage copy from `denoland/deno`.
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

Skipped request (in `requests.jsonl`):
```json
{
  "timestamp": "2026-06-01T16:16:39.195279+03:00",
  "level": "INFO",
  "message": "Request completed",
  "event": "request_completed",
  "request_id": "3df4888f",
  "url": "https://youtu.be/abc",
  "platform": "youtube",
  "duration_ms": 17351,
  "success": false,
  "skip_reason": "size_limit",
  "content_type": null,
  "file_size_mb": null,
  "user": {"id": 123, "name": "John", "username": "john"},
  "chat": {"id": -100, "name": "Group", "type": "group"}
}
```

Possible `skip_reason` values: `playlist`, `unsupported`, `size_limit`, `auth_required`, `metadata_failed`, `fetch_failed`, `download_failed`.

Reply-to-retry uses `"event": "reply_to_retry_received"` / `"reply_to_retry_completed"` and `"message": "Reply to retry received/completed"`.

Guest request received (in `requests.jsonl`):
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "Guest request received",
  "event": "guest_request_received",
  "request_id": "8e314411",
  "guest_query_id": "2697475888970155636",
  "url": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/",
  "user": {"id": 12345678, "name": "Alice", "username": "user_alice"},
  "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"},
  "reply": null
}
```

Guest request with reply:
```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "Guest request received",
  "event": "guest_request_received",
  "request_id": "8e314411",
  "guest_query_id": "2697475888970155636",
  "url": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/",
  "user": {"id": 12345678, "name": "Alice", "username": "user_alice"},
  "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"},
  "reply": {"user_id": 87654321, "name": "Bob", "username": "user_bob", "message": "check this"}
}
```

Guest request completed (in `requests.jsonl`):
```json
{
  "timestamp": "2026-06-10T20:42:04.768463+03:00",
  "level": "INFO",
  "message": "Guest request completed",
  "event": "guest_request_completed",
  "request_id": "8e314411",
  "guest_query_id": "2697475888970155636",
  "url": "https://vt.tiktok.com/ZS9Gg6dGp/",
  "platform": "tiktok",
  "duration_ms": 4725,
  "success": true,
  "cache": false,
  "content_type": "video",
  "file_size_mb": 3.65,
  "user": {"id": 12345678, "name": "Alice", "username": "user_alice"},
  "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}
}
```

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

Service events: `bot_started`, `bot_stopped`, `new_user_started`, `bot_added_to_chat`, `bot_rejected_group_addition`, `bot_removed_from_chat`, `bot_added_as_admin`, `bot_admin_rights_changed`, `bot_removed_as_admin`, `user_blocked_bot`, `unauthorized_access` (includes guest mode unauthorized with `"command": "guest"`).

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

Cache detail logs (in `request-details.jsonl`):
```json
{
  "timestamp": "2026-06-30T14:18:08.307392+03:00",
  "level": "INFO",
  "message": "Cached: tiktok:7647759526040489234",
  "url": "https://vm.tiktok.com/ZNRvwVjx8/",
  "request_id": "04ebc3a5",
  "cache_key": "tiktok:7647759526040489234"
}
```
```json
{
  "timestamp": "2026-06-30T14:18:28.680456+03:00",
  "level": "INFO",
  "message": "Cache hit: tiktok:7647759526040489234",
  "url": "https://vm.tiktok.com/ZNRvwVjx8/",
  "request_id": "04ebc3a6",
  "cache_key": "tiktok:7647759526040489234"
}
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MODE` | `development` | `development`/`dev` or `production`/`prod`. Determines log file name. |
| `LOG_OUTPUT` | `both` | `console` (or `stdout`), `file`, or `both`. Controls output destinations. |
| `LOG_DIR` | `logs` | Directory for log files |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL`. Set to `DEBUG` in dev to see detail logs. |

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

# Skipped requests (by reason)
cat logs/requests.jsonl | jq 'select(.skip_reason == "size_limit")'
cat logs/requests.jsonl | jq 'select(.skip_reason == "auth_required")'
cat logs/requests.jsonl | jq 'select(.skip_reason == "playlist")'
cat logs/requests.jsonl | jq 'select(.skip_reason == "unsupported")'

# All skipped requests
cat logs/requests.jsonl | jq 'select(.skip_reason != null)'

# Slow downloads (>5 seconds)
cat logs/requests.jsonl | jq 'select(.event == "request_completed" and .duration_ms > 5000)'

# Request lifecycle for a specific request_id (across both files)
cat logs/requests.jsonl | jq 'select(.request_id == "3df4888f")'
cat logs/request-details.jsonl | jq 'select(.request_id == "3df4888f")'

# Reply-to-retry requests
cat logs/requests.jsonl | jq 'select(.event | test("reply_to_retry"))'

# Guest mode requests
cat logs/requests.jsonl | jq 'select(.event | test("guest_request"))'

# Guest requests with reply context
cat logs/requests.jsonl | jq 'select(.event == "guest_request_received" and .reply != null)'

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

**Image:** Multi-stage build -- build stage compiles Python deps, runtime stage is Python 3.12-slim with yt-dlp, gallery-dl, ffmpeg, and deno (JS runtime).

**Container:**
- Runs as non-root `appuser`
- `restart: unless-stopped` -- survives reboots
- Env vars loaded from `.env` file
- Logs written to a bind-mounted `logs/` directory

**Volumes:**
- `./logs:/usr/src/app/logs` -- persistent structured JSON logs
- `bot-cache:/usr/src/app/data` -- SQLite media cache (named volume)
- `./ig-cookies.txt:/usr/src/app/ig-cookies.txt:ro` -- Instagram cookies (Netscape format, generated by ig_login_local.py)
- `./ig-session.json:/usr/src/app/ig-session.json:ro` -- Instagram instagrapi session state
- `./allowed-users.json:/usr/src/app/allowed-users.json:ro` -- user allowlist (read-only)
- `bot-downloads:/tmp/bot-downloads` -- temp download directory (named volume)

**Deploying updates:**
```bash
./bot.sh compose  # Rebuilds image (no cache) and restarts container
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

Both bots share the same group chats and test topics. This lets you test changes locally before pushing to production -- send the same URL to both bots and compare behavior.

**Typical workflow:**
1. Make changes locally, run `python -m pytest tests/ -v`
2. Rebuild dev bot: `docker compose up -d --build`
3. Test in shared group -- both bots receive the same messages
4. If dev bot works correctly, push and deploy to prod
