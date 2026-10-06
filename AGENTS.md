# Agents Guide

Entry point for AI agents working on this project. Start here to understand the codebase before making changes.

## What This Project Is

A Telegram bot that downloads videos and images from YouTube, TikTok, and Instagram. Users paste a URL, get the media back. Also silently attempts gallery-dl for 100+ other services (Pinterest, Pixiv, X, Reddit, DeviantArt, etc.) — works as a best-effort fallback.

**Tech stack:** Python 3.14+, uv, python-telegram-bot, yt-dlp (subprocess), gallery-dl (subprocess), pytest

## Documentation

For detailed documentation, see `docs/README.md` (human-readable overview) and the following module docs:

- `docs/group-chats/` - How bot works in groups
- `docs/guest-mode/` - Bot API 10.0 guest mode
- `docs/p2p-chats/` - Private chat behavior
- `docs/logs/` - Logging system
- `docs/content-delivery/` - Media downloading
- `docs/cache/` - Media cache for guest mode
- `docs/cookies.md` - Manual cookie setup/refresh (Instagram + TikTok + YouTube) and admin bot upload

## Project Structure

```
media-downloader-bot/
├── src/                # Application code
│   ├── bot.py          # Entry point - creates Application, registers handlers, runs polling
│   ├── config.py       # Loads .env, exports settings as constants
│   ├── downloader.py   # yt-dlp subprocess wrapper (metadata, download, audio, images, DownloadError)
│   ├── platform_args.py # Platform-specific yt-dlp constants (USER_AGENT, COMMON_YTDL_ARGS, TIKTOK_REFERER)
│   ├── handlers.py     # Telegram handlers: /audio, URL message handling (thin orchestrator)
│   ├── cookie_upload.py # Admin-only cookie upload: handle_cookie_document() (P2P document messages)
│   ├── guest.py        # Bot API 10.0 guest mode: handle_guest(), download pipeline, InlineQueryResult builders
│   ├── auth.py         # Authorization checks (is_authorized, is_group_chat, allowlists)
│   ├── commands.py     # User commands: /start, /help, /caption
│   ├── telegram_utils.py # Telegram helpers: typing_indicator, send_images
│   ├── messages.py     # User-facing message constants (MSG_*) used across all handlers
│   ├── logging_config.py # Structured JSON logging: four-file split (requests, details, service, errors)
│   ├── cache.py          # SQLite media cache for guest mode (URL extraction, key generation, store/retrieve)
│   ├── platforms/       # Platform-specific download logic
│   │   ├── __init__.py # detect_platform(), extract_domain(), SUPPORTED_PLATFORMS dict
│   │   ├── youtube.py  # YouTube/YT Music download + format picker callback
│   │   ├── tiktok.py   # TikTok download with gallery-dl fallback
│   │   └── instagram.py # Instagram images with gallery-dl fallback
│   └── utils.py        # URL validation, file cleanup, get_gallery_dl_domains()
├── bot.sh              # Script menu + arg routing for all scripts (deploy/update/compose/dev/pull-logs/version)
├── scripts/
│   ├── shell/          # Shell scripts
│   │   ├── compose.sh
│   │   ├── update.sh
│   │   └── pull-logs.sh
│   └── python/         # Python utility scripts
│       ├── generate_gallery_dl_domains.py
│       └── generate_ytdlp_domains.py
├── tests/              # Test suite (imports from src/ via conftest.py)
│   ├── test_handlers.py
│   ├── test_commands.py
│   ├── test_auth.py
│   ├── test_telegram_utils.py
│   ├── test_youtube.py
│   ├── test_tiktok.py
│   ├── test_guest.py
│   ├── test_downloader.py
│   ├── test_cache.py
│   ├── test_cookie_upload.py
│   └── test_logging.py
├── docs/
│   ├── README.md       # Project overview
│   └── README.md       # Module responsibilities and data flow
├── logs/               # Persistent log files (gitignored, mounted as volume)
├── pyproject.toml      # Project metadata, version, dependencies (uv)
├── uv.lock             # Locked dependency versions
├── .python-version     # Python version pin for uv (3.14)
├── .env.example        # Config template
├── Dockerfile          # Multi-stage build (Python 3.14-slim, yt-dlp, gallery-dl, ffmpeg, deno JS runtime)
├── docker-compose.yml  # Container orchestration with volume mounts
├── .dockerignore       # Excludes .venv, __pycache__, logs, cookies.txt from build
└── conftest.py         # Adds src/ to Python path for tests
```

## Module Responsibilities

| Module | Depends on | What it does |
|---|---|---|
| `src/config.py` | .env file, allowed-users.json | Loads BOT_TOKEN, BOT_ADMIN_IDS, ALLOWED_USER_IDS (merged from JSON + env), ALLOWED_GROUP_IDS, DOWNLOAD_DIR, MAX_FILE_SIZE, MAX_CONCURRENT_DOWNLOADS, IG_COOKIES_PATH, TIKTOK_COOKIES_PATH, COOKIES_DIR, YT_COOKIES_PATH, GUEST_MODE_ENABLED, STORAGE_CHANNEL_ID, MODE, LOG_OUTPUT, LOG_DIR, LOG_LEVEL |
| `src/auth.py` | config | Authorization: `is_authorized()`, `is_bot_admin()`, `was_notified()`, `mark_notified()`, `was_notified_guest()`, `mark_notified_guest()`, `is_group_chat()`, `_is_allowed()`, `_is_allowed_group()` |
| `src/messages.py` | nothing | User-facing message constants: `MSG_UNAUTHORIZED`, `MSG_TIKTOK_LOGIN_REQUIRED`, `MSG_FETCH_FAILED`, `MSG_IMAGE_POST_FETCH_FAILED`, `MSG_SIZE_LIMIT`, `MSG_CAPTION_ENABLED/DISABLED`, `MSG_START`, `MSG_HELP`, etc. All `reply_text()` and `_text_result()` strings import from here. |
| `src/commands.py` | auth, config, messages, logging_config | User commands: `start_command()`, `help_command()`, `caption_command()`, `get_caption_for_user()` — all use notification tracking for unauthorized users |
| `src/telegram_utils.py` | nothing | Telegram helpers: `typing_indicator()` context manager, `send_images()` for single/batched photo replies |
| `src/platforms/__init__.py` | nothing | Platform detection: `detect_platform()`, `extract_domain()`, `SUPPORTED_PLATFORMS` dict |
| `src/platforms/youtube.py` | downloader, commands, telegram_utils | YouTube/YT Music: `handle_youtube()`, `handle_ytmusic()` (format keyword in message skips the picker), `_send_format()` (shared audio/video/both execution), `ytmusic_callback()`, format picker |
| `src/platforms/tiktok.py` | downloader, platform_args, telegram_utils | TikTok: `handle_tiktok()` — photo-post extractor first (`download_tiktok_photo_images()`), then metadata/gallery-dl fallback for video posts |
| `src/platforms/instagram.py` | downloader, telegram_utils | Instagram: `handle_instagram()` with gallery-dl fallback and cookies |
| `src/utils.py` | nothing | URL validation, file cleanup, `parse_format_choice()` (format keywords video/відео/видео, audio/аудіо/аудио → `"video"`/`"audio"`/`"both"`/None), `get_gallery_dl_domains()` (imports/auto-generates gallery-dl domain whitelist) |
| `src/downloader.py` | yt-dlp, gallery-dl, platform_args | yt-dlp subprocess calls: `_run_ytdlp()` helper (common flags via COMMON_YTDL_ARGS), `_youtube_cookies(url)` (returns YT_COOKIES_PATH for YouTube URLs when the file exists), `_build_format_selector()` (codec-priority -f ladder: H.264 → AV1/VP9 → catch-all; size-capped branches descend the quality ladder; `progressive_first=True` for Instagram) + `VIDEO_FORMAT_SELECTOR`/`INSTAGRAM_FORMAT_SELECTOR` constants, `get_metadata()` (optional `format_selector` for accurate size estimates, 60s timeout, logs stderr on failure, raises `DownloadAuthRequired` for age-restricted; falls back to YouTube cookies for YouTube URLs), `download_video()` (picks selector by `platform`, retries with lower quality, applies faststart via `_apply_faststart()`, raises `DownloadAuthRequired`/`DownloadError`; adds YouTube cookies for YouTube URLs), `download_audio()` (adds YouTube cookies for YouTube URLs), `download_images()`, `download_gallery_dl_images()`, `download_gallery_dl_video()`, `download_tiktok_photo_images()` (TikTok photo-post pipeline: resolves short links, rewrites `/photo/`→`/video/`, runs `yt-dlp --write-pages` and parses `imagePost` gallery URLs from the rehydration dump, downloads images via httpx; falls back to gallery-dl; raises `DownloadError(MSG_IMAGE_POST_FETCH_FAILED)` when a known photo post cannot be extracted at all; returns `[]` for non-photo URLs). Raises `DownloadAuthRequired` when content requires login (age-restricted YouTube, TikTok login-gated). Raises `DownloadError` on gallery-dl timeout (user_message + raw_error for logging). |
| `src/platform_args.py` | nothing | Platform-specific yt-dlp constants: `USER_AGENT` (Chrome 140), `COMMON_YTDL_ARGS` (`--no-playlist`, `--user-agent`), `TIKTOK_REFERER` (Referer header for WAF bypass). Imported by downloader.py and platform handlers. |
- `src/logging_config.py` | config | Structured JSON logging: four-file split (requests/details/service/errors), JSONFormatter, `_enrich_chat()` for enriched chat dicts, `log_error()` for unhandled exceptions, filter-based routing, with_request_logging decorator (reads `_skip_reason` from user_data), contextvars for request_id, request lifecycle functions (log_request_received/completed/failed — completed accepts `skip_reason`), guest request functions (log_guest_request_received/completed), service log functions (log_new_user, log_bot_added_to_chat, log_bot_rejected_group_addition, log_bot_admin_lookup, log_bot_removed_from_chat, log_admin_rights_changed, log_user_blocked_bot, log_unauthorized_access, log_cookie_updated) |
| `src/cache.py` | logging_config | SQLite media cache: `get_cached()` returns (file_id, media_type) by URL/platform (optional `variant` param appends a key suffix, e.g. `youtube:{id}:audio` so audio and video entries coexist), `store()` saves download result, URL-based ID extraction for TikTok/YouTube/Instagram, metadata hash fallback, `get_stats()`, `cleanup_older_than()`. For TikTok short URLs, follows HTTP redirects to resolve video ID for cache key. |
| `src/handlers.py` | auth, commands, platforms, telegram_utils, downloader, logging_config | Thin orchestrator: `handle_url()` (clears stale `_platform`, filters pure playlist URLs, reply-to-retry, gallery-dl fallback, unauthorized reply-to-bot check in groups), `handle_gallery_dl_fallback()`, `audio_command()`, `_download_and_send()` (sets `skip_reason` on failure: `unsupported`, `size_limit`, `auth_required`, `metadata_failed`, `fetch_failed`, `download_failed`), `my_chat_member_handler()` (handles bot added/removed/promoted/demoted/blocked, admin check for group additions) |
| `src/guest.py` | auth, config, downloader, platforms, utils, logging_config, httpx, cache | Bot API 10.0 guest mode: `handle_guest()` receives guest_message updates, extracts URLs (from tag text or replied-to message), parses format keyword (`video`/`відео`/`видео` → `force_video`), downloads via platform handlers, uploads to storage channel for file_id, replies via `answer_guest_query()`. Uses raw dicts for InlineQueryResult to avoid ptb placeholder URL issues. `music.youtube.com` URLs download audio by default via `_download_audio()` (MP3 → `sendAudio` → `_audio_result()`); `force_video=True` selects video. Caches file_ids via `cache.get_cached()`/`cache.store()` — cache hit skips download+upload entirely; audio results use cache variant `"audio"`. Fetches TikTok metadata for short URL deduplication. Unauthorized users without URL are silently ignored; unauthorized users with URL get "You are not authorized" once via `answer_guest_query`, then silently ignored. Uses `was_notified_guest()`/`mark_notified_guest()` (separate from P2P tracking). Reply to bot message without URL is silently ignored. Logs unauthorized access to service.jsonl via `log_unauthorized_access()`. For gallery-dl supported domains (e.g. deviantart, pinterest), falls back to `_gallery_dl_result()` when platform is not in SUPPORTED_PLATFORMS. Platform logged from `extract_domain(url)` for non-primary platforms. Photo upload handles Telegram's list-of-PhotoSize response. Uses `_safe_answer_guest_query()` to handle deleted messages gracefully (catches BadRequest when user deletes message before bot answers). For TikTok, `_download_media_result()` tries `download_tiktok_photo_images()` before `download_video()` (photo posts cannot be downloaded as video); `_upload_photo_result()` builds the photo/media-group result. Error replies: `DownloadError` → `e.user_message`; `ValueError` → `str(e)` (all pipeline raise sites use MSG_* constants); any other exception → generic `MSG_DOWNLOAD_FAILED` so internals never reach users. |
| `src/cookie_upload.py` | auth, config, logging_config, messages | Admin-only cookie upload: `handle_cookie_document()` handles `.txt` documents in P2P chats only (groups/guest/inline ignored). Flow: private-chat check → `is_bot_admin()` (non-admins silently ignored) → caption `cookie update <tt|ig|yt>` (`MSG_COOKIE_CAPTION_EMPTY` / `MSG_COOKIE_INVALID_CAPTION`) → `.txt` + Netscape content check (`MSG_COOKIE_INVALID_FILE`) → saves `cookies/<platform>-cookie-YYYY-MM-DD.txt` + overwrites active path → replies `MSG_COOKIE_UPDATED` → `log_cookie_updated()` to service.jsonl. |
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
5. Unsupported URLs filtered against gallery-dl domain whitelist (`get_gallery_dl_domains()`). Domains not in the list are skipped instantly (logged with `skip_reason: "unsupported"`)
6. YouTube URLs: pure playlists (`list=` without `v=`) silently skipped. Single videos in playlists: `list=` stripped, metadata fetched with `--no-playlist`. Metadata fetched silently (no typing indicator), size checked against 50MB limit. Age-restricted videos raise `DownloadAuthRequired` → `skip_reason: "auth_required"`
6. Reply-to-retry: user replies to message with URL and mentions bot → handled inside `handle_url()` (extracts URL from replied message, retries download)
7. `handlers.py` detects platform via `platforms.detect_platform()`
8. Delegates to platform-specific handler:
   - YouTube → `platforms.youtube.handle_youtube()` or `handle_ytmusic()` (format keyword in message skips the picker)
   - TikTok → `platforms.tiktok.handle_tiktok()` (photo-post extractor first via `download_tiktok_photo_images()`, then gallery-dl fallback)
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
    - Bot added to group: checks bot admin → allow; no bot admin in group → reject; anonymous admin → allow if bot admin present; allowed user → allow; group admin with invite rights → allow; otherwise reject + leave
    - Bot removed/promoted/demoted: logged to service.jsonl
    - User blocks bot (private chat): logged as `user_blocked_bot`
14. **Guest mode** (`GUEST_MODE_ENABLED=true`): User mentions `@botname` in any chat → Telegram sends `guest_message` update → `guest.handle_guest()`:
    - Caller identified via `guest_msg.from_user` (Telegram sends `from`, ptb maps to `from_user`)
    - URL extracted from tag text OR replied-to message (before auth check)
    - If no URL: authorized users get "Please include a URL" hint; unauthorized users silently ignored
    - Auth check via `is_user_allowed(caller_id)` (same allowlist as regular messages) — only when URL present
    - **Unauthorized guest with URL**: first attempt → "You are not authorized" via `answer_guest_query` + `log_unauthorized_access` to service.jsonl; subsequent → silently ignored. Uses `was_notified_guest()`/`mark_notified_guest()` (separate from P2P tracking)
    - Reply to bot message without URL → silently ignored (no error message)
    - Reply to bot message with no text → shows media type (e.g. `[photo]`, `[video]`) in logs
    - `log_guest_request_received()` logs to `requests.jsonl` with user, chat, reply context
    - Platform detected via `detect_platform()`. If None, falls back to `extract_domain(url)` for logging (e.g. "deviantart.com")
    - Download routed via `_download_and_build_result()`:
      - **Cache check first** via `cache.get_cached()` — hit returns cached `file_id` instantly (cache variant `"audio"` for music audio requests)
      - YouTube → `_download_youtube()`; `music.youtube.com` without a video keyword → `_download_audio()` (audio default)
      - TikTok/Instagram → `_download_media_result()` (TikTok tries `download_tiktok_photo_images()` first — photo posts can't be video — then fetches metadata for short URL dedup)
      - Gallery-dl supported domain → `_gallery_dl_result()` (checks `get_gallery_dl_domains()` whitelist)
      - Unsupported domain → "Unsupported platform"
    - After successful download, result cached via `cache.store()`
    - File uploaded to storage channel (`STORAGE_CHANNEL_ID`) to get `file_id`. Photo responses handled as list (Telegram sends PhotoSize array).
    - Reply via `answer_guest_query()` with InlineQueryResult (raw dict with `video_file_id`/`photo_file_id`). Single photo only — inline results don't support media groups.
    - `log_guest_request_completed()` logs success/failure, platform, duration, cache hit/miss to `requests.jsonl`
    - **Handler order**: guest handler registered BEFORE text handler because `filters.TEXT` matches guest messages via `effective_message`
15. **Unauthorized reply to bot in groups**: In `handle_url()`, if a user replies to a bot message in a group and is not in the allowlist (`_is_allowed()`), the message is silently ignored. This prevents unauthorized users from triggering downloads by replying to bot messages in groups.
16. **Cookie upload**: Bot admin sends a `.txt` document in P2P with caption `cookie update <tt|ig|yt>` → `cookie_upload.handle_cookie_document()` validates chat/admin/caption/file, saves `cookies/<platform>-cookie-<date>.txt` + active copy, replies confirmation, logs `cookies_updated` to service.jsonl. Non-P2P chats and non-admins are silently ignored.

## Key Design Decisions

- **yt-dlp as subprocess** - Not imported as Python library. Keeps yt-dlp independently upgradable.
- **Stateless bot** - No database. Temp files cleaned after upload. Notification tracking (`_already_told_users`) resets on restart.
- **Auto best quality** - Downloads best quality under 50MB Telegram limit, retries with worst on failure.
- **Codec compatibility (iOS)** - Format selectors prefer H.264 (`vcodec^=avc1`) because it is the only codec every Telegram client decodes (iOS AVPlayer has no VP9; most iPhones have no AV1) — `ext=mp4` does NOT imply H.264: Instagram DASH ships VP9 and YouTube ships AV1 in mp4 containers. Size-capped branches come first so yt-dlp drops over-limit rungs and descends the quality ladder (1080p > 50MB → 720p → 480p → ...); each codec phase falls through to the next (H.264 → AV1/VP9 → catch-all) so a video is always sent rather than an error. Instagram uses `INSTAGRAM_FORMAT_SELECTOR` (`platform="instagram"`, progressive-first): its H.264 rendition has no vcodec metadata while its DASH ladder is VP9-only, so the bare progressive branch must precede the VP9 DASH merge (otherwise iPhone Telegram shows only a blurred preview with sound).
- **User allowlist** - IDs merged from `allowed-users.json` (array of objects with `id` field) + `ALLOWED_USER_IDS` env var. If no sources configured = allow all. If sources configured but user not in list = deny.
- **Bot admins** - `BOT_ADMIN_IDS` env var (comma-separated). Admins can always add bot to groups. Empty = anyone can add.
- **Unauthorized user handling** - First attempt: "You are not authorized" + log `unauthorized_access` event. Subsequent attempts: silently ignored (in-memory sets, resets on restart). P2P and guest mode track separately — a user told in P2P can still use guest mode and vice versa. Guest mode only shows auth message when URL is present; without URL, unauthorized users are silently ignored.
- **Group security** - Relaxed group addition: bot admins can always add; anonymous admins and allowed users can add if a bot admin is in the group; group admins with invite rights can add if a bot admin is in the group. No bot admin in group → reject. **Gotcha:** the bot-admin-presence check uses `getChatMember`, which is only guaranteed when the bot itself is an admin — a bot admin acting as an *anonymous admin* may fail to resolve, causing a false rejection (bot replies "Not everyone can add me to groups" and leaves). Workaround: disable anonymous mode for that admin before adding the bot. Each presence-check lookup is logged to service.jsonl as `bot_admin_lookup` (status or error) so failed lookups are diagnosable. The presence check accepts `administrator`/`member`/`creator` statuses. See `docs/group-chats/admin-controls.md#known-gotchas`.
- **Structured logging** - Four JSON log files: `requests.jsonl` (request lifecycle), `request-details.jsonl` (intermediate download steps), `service.jsonl` (bot events), `errors.jsonl` (unhandled exceptions with error_id). `_enrich_chat()` normalizes chat dicts with name/username. Filter-based routing by logger name. Zero external dependencies.
- **User-facing messages** - All `reply_text()` and `_text_result()` strings centralized in `src/messages.py` as `MSG_*` constants. No inline string literals in handlers.
- **DownloadAuthRequired** - Custom exception raised by `download_video()` or `get_metadata()` when yt-dlp reports content requires login (e.g. age-restricted YouTube, TikTok login-gated). Caught at orchestrator level (`_download_and_send`, `_download_media_result`), not inside platform handlers. Sets `skip_reason: "auth_required"` in logs. Shows "This content is restricted. Login required to access" to user.
- **DownloadError** - Custom exception for transient download failures (e.g. gallery-dl timeout). Carries `user_message` (safe for users, from MSG_* constants) and `raw_error` (technical details for logging to request-details.jsonl). Caught at orchestrator level (`_download_and_send`, `handle_guest`), not inside platform handlers. Ensures consistent error messages across P2P, group, and guest contexts.
- **TikTok photo-post pipeline** - yt-dlp's TikTok extractor does not match `/photo/` URLs and has no `imagePost` gallery support; gallery-dl (the only tool that understands photo posts) has been 403-blocked by TikTok's anti-bot since ~September 2026. The bot instead runs `yt-dlp --write-pages` against the `/video/` form of the URL (yt-dlp's challenge-cookie fetch still works) and parses the gallery URLs from the `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON dump. gallery-dl is kept only as a safety net; when a known photo post cannot be extracted at all, `download_tiktok_photo_images()` raises `DownloadError(MSG_IMAGE_POST_FETCH_FAILED)` ("Could not fetch this image post") and skips the doomed yt-dlp video attempts (which can never work on `/photo/` URLs).
- **uv dependency management** - `pyproject.toml` + `uv.lock` (committed) replace `requirements.txt`. Runtime deps in `[project] dependencies`, dev tools (pytest, pytest-asyncio, yt-dlp) in the `dev` group. Project version lives in `pyproject.toml` (`uv version --bump patch`; `./bot.sh version` reads it). Local commands run via `uv run …`. Add/update deps with `uv add`/`uv lock --upgrade-package <name>`.
- **Docker deployment** - Multi-stage build with yt-dlp, gallery-dl, ffmpeg, and deno (JS runtime for yt-dlp YouTube extraction). Build stage runs `uv sync --frozen --no-dev` into a `.venv` copied to the runtime; runtime stage pip-installs yt-dlp (from master) and gallery-dl (pinned) separately. Persistent logs via volume mount to `./logs/`. `allowed-users.json` mounted read-only.
- **Platform separation** - Each platform (YouTube, TikTok, Instagram) has its own module with isolated download logic.
- **Guest mode (Bot API 10.0)** - Users mention `@botname` in any chat to download media. Uses `guest_message` updates + `answerGuestQuery()`. Files uploaded to a private storage channel to get `file_id`s for InlineQueryResult. Guest handler registered before text handler to prevent `filters.TEXT` from consuming guest updates.
- **InlineQueryResult as raw dicts** - ptb's `InlineQueryResultVideo`/`Photo` constructors require placeholder URLs that Telegram tries to fetch. Using raw dicts with `video_file_id`/`photo_file_id`/`audio_file_id` avoids this.
- **Media cache** - SQLite cache stores Telegram `file_id`s by platform-specific content ID. Cache hit skips download+upload entirely. TikTok metadata fetched for short URL deduplication. For short URLs, follows HTTP redirects to resolve video ID. Falls back to URL hash when redirect fails. Cache persists in Docker volume.
- **Format keywords** - A message word `video`/`відео`/`видео` or `audio`/`аудіо`/`аудио` (case-insensitive, `parse_format_choice()`) selects the format for `music.youtube.com` links only. P2P/groups: keyword skips the format picker and sends directly; both keyword families → both formats. Guest mode: music links default to audio, video keyword selects video, both keywords resolve to audio (single inline result only). Regular `youtube.com` links always download video and ignore keywords.
- **Instagram cookies (browser export)** - Cookies are exported from a browser as Netscape format and uploaded by a bot admin (`cookie update ig`) or placed manually as `ig-cookies.txt`. No automated login: instagrapi and `scripts/python/ig_login_local.py` (`./bot.sh refresh-ig`) were removed. Auto-renewal (staleness check, cron, refresh-on-update) was removed earlier — it could not detect server-side session invalidation.
- **Cookie upload via bot** - Bot admins update cookie files by sending a `.txt` document in a P2P chat with caption `cookie update <tt|ig|yt>` (keyword case-insensitive, platform lowercase-only). Saved as dated file `cookies/<platform>-cookie-<YYYY-MM-DD>.txt` (history, gitignored dir mounted into container) plus an overwrite of the active path the code reads. Non-admins, groups, guest, and inline are silently ignored. Rejects: empty caption → "Caption cannot be empty", bad keyword → "Invalid caption", bad file → "Invalid file". Success logs `cookies_updated` event to service.jsonl.
- **TikTok cookies** - Browser-exported Netscape cookies (`tiktok-cookies.txt`) passed to yt-dlp and gallery-dl for TikTok URLs. Enables downloading age-restricted and login-gated content. Cookie file mounted as writable volume (yt-dlp writes back to update cookies). Configurable via `TIKTOK_COOKIES_PATH` env var. Cookies expire ~30 days and must be manually refreshed.
- **Guest error replies** - `handle_guest` replies the specific message for three failure classes: `DownloadError` → `e.user_message`; `ValueError` → `str(e)` (every pipeline raise site uses an `MSG_*` constant, e.g. "Could not download media from this URL"); any other exception → generic `MSG_DOWNLOAD_FAILED` so internals never reach users. (Previously all `ValueError`s were swallowed into "Download failed", hiding the specific text.)
- **Deleted message handling** - All `reply_parameters` dicts include `allow_sending_without_reply=True`. When user deletes their message before bot replies, bot sends message directly to chat instead of throwing `BadRequest`. Guest mode uses `_safe_answer_guest_query()` wrapper that catches `BadRequest` and logs gracefully.

## Security Rules

**NEVER** `git add`, `git commit`, or `git push` files under `docs/superpowers/` (specs, plans, design docs). These are internal AI working documents and must NEVER enter git history.

Never commit `allowed-users.json` — it contains user IDs and is generated locally by the get-user-ids script.

**NEVER commit real PII in documentation.** Do not use real usernames, user IDs, chat IDs, display names, or IP addresses in any tracked markdown files. Use fake placeholders (`user_alice`, `12345678`, `Test Group`, etc.).

## Running Tests

```bash
uv run pytest tests/ -v
```

All 537 tests use mocked subprocess calls - no real downloads needed.

## Common Tasks

**Add a new platform:** Create `src/platforms/newplatform.py` with a `handle_newplatform()` function, add domain to `SUPPORTED_PLATFORMS` in `src/platforms/__init__.py`, add platform-specific args in `src/downloader.py`. Register in `handlers.py` `_download_and_send()`.

**Add a new command:** Add handler function in `src/commands.py`, register in `src/bot.py` with `app.add_handler(CommandHandler(...))`.

**Change download behavior:** Edit `src/downloader.py` for yt-dlp changes, or the platform-specific handler in `src/platforms/` for platform logic.

**Add a new bind mount (folder or file) to `docker-compose.yml`:** The Docker daemon auto-creates missing mount sources as **root**, and the container user (`appuser`, uid 1000) then cannot write them — the failure shows up as `PermissionError: [Errno 13]` in `errors.jsonl` at runtime. Prevent it BEFORE the mount ships:
1. **Directory:** commit a `.gitkeep` inside it and un-ignore it (see the `/cookies/*` + `!/cookies/.gitkeep` pattern in `.gitignore`) so fresh clones get a user-owned dir.
2. **File:** pre-create it (empty if needed) as the invoking user in `scripts/shell/compose.sh` (see the existing loop before `docker compose up`).
3. **Existing server where Docker already created the path as root:** for an empty dir, `rmdir` + `mkdir` as the deploy user; for a file, `sudo chown 1000:1000 <path>`. Then `docker compose up -d --force-recreate` — a running container keeps the old (root-owned) inode even after you replace the path on the host.
Also verify writability from inside the container: `docker compose exec bot sh -c 'touch <mount-path>/.wtest && rm <mount-path>/.wtest'`.

**Docker tool versions:** `gallery-dl` is pinned to 1.32.4 in the Dockerfile. Version 1.32.9+ has a TikTok regression (403 Forbidden) — retested 2026-09-26 against 1.32.13 on 4 known-failing TikTok photo URLs: 1.32.13 failed all 4 (403) while 1.32.4 succeeded on 1. Do NOT upgrade without testing TikTok first. `yt-dlp` installs from master with curl-cffi for TikTok impersonation support.

**Add logging to a handler:** Apply `@with_request_logging` decorator from `logging_config`. The decorator automatically logs request lifecycle (received/completed/failed).

**Setup for groups:** Disable privacy mode in @BotFather (`/setprivacy` → Disable). Optionally set `ALLOWED_GROUP_IDS` in .env to restrict which groups. Add bot to target groups.

**Run with Docker:**
```bash
cp .env.example .env  # Add BOT_TOKEN
docker compose up -d --build
docker logs -f media-downloader-bot  # Watch logs
```

**View persistent logs:** Logs are written to `./logs/` on the host (mounted as volume). Files: `requests.jsonl` (request lifecycle), `request-details.jsonl` (download steps), `service.jsonl` (bot events). Append `.dev.jsonl` for MODE=development.

**Deploy to production:**
```bash
./bot.sh deploy
```
Run this from the project root on the current host. **Do NOT run raw SSH commands or `docker compose` manually** — `./bot.sh deploy` is the only correct deploy command.

**Deploy timing:** `./bot.sh deploy` runs remotely and can take several minutes. Run it and return without waiting for it to finish — the script handles everything internally.

## Production Environment

**The bot runs on a remote server, not locally.** Local `docker ps` will always show nothing — the production container lives on the remote server. See `docs/deploy.md` for server details.

### Pulling Logs for Debugging

**Before analyzing ANY errors, pull production logs first:**
```bash
./bot.sh pull-logs
```
This copies today's logs from the server into local `logs/YYYY-MM-DD/`. Then read those files.

**Do NOT** read `logs/*.dev.jsonl` for production issues — those are local dev bot logs.

### Quick Debugging Commands

```bash
# Pull logs
./bot.sh pull-logs

# See docs/deploy.md for SSH commands to check container status, tail logs, etc.
```

## Docs Index

- [Project Overview](docs/README.md) - Quick summary of what/why, architecture, and links to detailed docs
- [Deployment](docs/deploy.md) - Production server, SSH access, deploy commands (gitignored)
- [Guest Mode](docs/guest-mode/README.md) - Bot API 10.0 guest mode overview and technical reference
- [Cookies](docs/cookies.md) - Manual cookie setup/refresh (Instagram + TikTok) and troubleshooting
