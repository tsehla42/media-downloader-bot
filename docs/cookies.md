# Cookie System

The bot supports cookies for both Instagram and TikTok to enable authenticated downloads.

## Instagram Cookie Refresh System

Instagram image downloads via gallery-dl require authentication cookies. The bot includes a full cookie refresh system that handles login, session persistence, staleness checking, and automated renewal via cron.

## TikTok Cookies

TikTok requires authentication for age-restricted and login-gated content. Unlike Instagram, TikTok cookies are manually exported from a browser and refreshed periodically.

### Setup

1. Log into TikTok in a desktop browser (Chrome, Firefox, etc.)
2. Install "Get cookies.txt LOCALLY" extension ([Chrome](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc))
3. Export cookies for `tiktok.com` as Netscape format
4. Place file as `tiktok-cookies.txt` in project root
5. Set `TIKTOK_COOKIES_PATH=tiktok-cookies.txt` in `.env` (optional, default is correct)

### How It Works

- `get_metadata()` receives `cookies=TIKTOK_COOKIES_PATH` for TikTok URLs
- `download_video()` receives `--cookies` flag when `platform="tiktok"`
- `download_gallery_dl_images()` receives cookies for TikTok photo posts
- Cookie file is mounted as writable volume (yt-dlp writes back to update cookies)

### Cookie Expiration

Cookies expire after ~30 days. When expired, TikTok downloads will fail with auth errors. Refresh by re-exporting from browser.

### Setup

1. Export cookies from browser (see above)
2. Place `tiktok-cookies.txt` in project root
3. Rebuild and restart:

```bash
docker compose up -d --build
```

The container picks up the new file via volume mount in `docker-compose.yml`:

```yaml
volumes:
  - ./tiktok-cookies.txt:/usr/src/app/tiktok-cookies.txt
```

Note: Unlike Instagram cookies, TikTok cookies are mounted as **writable** (not `:ro`) because yt-dlp writes back to update cookies.

## Architecture

```
Host machine (must NOT be Docker)
├── .env                        # IG_USERNAME, IG_PASSWORD
├── ig-cookies.txt              # Netscape format cookies (gitignored, mounted into container)
├── ig-session.json             # instagrapi session state (gitignored, mounted into container)
└── crontab                     # Optional: auto-refresh every 7 days

scripts/python/
├── ig_login_local.py           # Login + export cookies (host only)
└── check_cookies.py            # Staleness check (exit code 0=fresh, 1=stale)

scripts/shell/
├── refresh-ig-cookies.sh       # Orchestrator: check → refresh if stale
└── update.sh                   # Git pull → refresh cookies → rebuild → restart

src/
└── cookies.py                  # Core logic: staleness check, login, Netscape export
```

### Why Host-Only?

Instagram detects and blocks logins from Docker containers. The `ig_login_local.py` script checks for `/.dockerenv` and refuses to run inside Docker. All login operations must happen on the host machine.

## Modules

### `src/cookies.py`

Core library used by both scripts and the bot:

- **`check_cookies_staleness(cookies_path, max_age_days=7)`** — Returns `True` if file is missing or older than threshold
- **`refresh_instagram_cookies(username, password, session_path, cookies_path, max_age_days=7, force=False)`** — Full refresh flow: checks staleness, logs in (session first, then fresh), exports cookies. Returns `True` if cookies are fresh or successfully refreshed. Preserves existing cookies on failure.
- **`_login_with_session(cl, username, password, session_path)`** — Tries saved session, falls back to fresh login
- **`_export_cookies_to_netscape(cookie_jar, output_path, domain)`** — Converts `RequestsCookieJar` to Netscape format (utility, not used in main flow — cookies are exported directly from `authorization_data`)

### `scripts/python/ig_login_local.py`

Standalone host-side login script:

1. Loads `IG_USERNAME` / `IG_PASSWORD` from `.env`
2. Detects Docker environment → refuses if inside container
3. Logs in via `instagrapi.Client`
4. Saves session to `ig-session.json`
5. Exports `sessionid` + `ds_user_id` to `ig-cookies.txt` (Netscape format)
6. Logs `ig_cookies_refreshed` event to `service.jsonl`

### `scripts/python/check_cookies.py`

Standalone staleness checker:

- Exit code `0` — cookies are fresh
- Exit code `1` — cookies are stale or missing
- Exit code `2` — error

### `scripts/shell/refresh-ig-cookies.sh`

Orchestrator used by `./bot.sh update` and `update.sh`:

1. Runs `check_cookies.py`
2. If fresh → skips
3. If stale → runs `ig_login_local.py`
4. Reports success/failure

## Setup

### 1. Install instagrapi on the host

```bash
pip install instagrapi python-dotenv
```

### 2. Configure credentials

Add to `.env`:

```
IG_USERNAME=your-dummy-ig-account
IG_PASSWORD=your-password
IG_COOKIES_PATH=ig-cookies.txt
IG_SESSION_PATH=ig-session.json
```

Use a throwaway Instagram account — this is just for API access.

### 3. Generate initial cookies

```bash
python scripts/python/ig_login_local.py
```

This creates `ig-cookies.txt` and `ig-session.json` in the project root.

### 4. Rebuild and restart

```bash
./bot.sh update    # or: ./bot.sh 2
```

The container picks up the new files via volume mounts in `docker-compose.yml`:

```yaml
volumes:
  - ./ig-cookies.txt:/usr/src/app/ig-cookies.txt:ro
  - ./ig-session.json:/usr/src/app/ig-session.json
```

## Refreshing Cookies

### Via ./bot.sh (recommended)

```bash
./bot.sh update           # check → refresh if stale → rebuild → restart
./bot.sh refresh-ig       # check → refresh if stale (no rebuild)
```

### Via update.sh (full update)

```bash
./bot.sh update   # git pull → refresh cookies → rebuild → restart
```

### Manually

```bash
python scripts/python/ig_login_local.py
docker compose restart
```

The container picks up the new `ig-cookies.txt` on the next request — no rebuild needed for cookie-only changes.

## Cron Job Setup

For automated cookie renewal, add a cron job on the **host machine** (not inside Docker).

### Recommended: Every 7 days

```bash
crontab -e
```

Add:

```
0 9 */7 * * cd /path/to/media-downloader-bot && ./bot.sh refresh-ig >> logs/cron.log 2>&1
```

This runs `refresh-ig-cookies.sh` (check → refresh if stale). Since cookies are bind-mounted into the container, no rebuild or restart is needed — the container picks up new cookies on the next request.

### Minimal: Check-only cron

If you prefer to refresh manually but want visibility:

```
0 9 * * * cd /path/to/media-downloader-bot && python scripts/python/check_cookies.py >> logs/cron.log 2>&1
```

This only checks staleness — you'll see `Fresh: 1.2 days old` or `Stale: 3.5 days old` in the log.

### Advanced: Check + conditional refresh

```
0 9 */7 * * cd /path/to/media-downloader-bot && python scripts/python/check_cookies.py || python scripts/python/ig_login_local.py >> logs/cron.log 2>&1
```

### Cron Job Reference

| Schedule | Command | What it does |
|----------|---------|-------------|
| `0 9 */7 * *` | `./bot.sh refresh-ig` | Check → refresh if stale (no rebuild) |
| `0 9 * * *` | `check_cookies.py` | Check only, logs staleness |
| `0 9 */7 * *` | `check \|\| login` | Check, refresh only if stale |

### Log Monitoring

Check cron output:

```bash
tail -20 logs/cron.log
```

Expected output for fresh cookies:

```
=== Media Downloader Bot Update ===
Pulling latest changes...
Already up to date.
Checking Instagram cookies...
Cookies are fresh.
Rebuilding and restarting bot...
...
=== Update complete ===
```

Expected output for stale cookies:

```
=== Media Downloader Bot Update ===
Pulling latest changes...
Already up to date.
Checking Instagram cookies...
Cookies are stale or missing. Refreshing...
Logging in as your-username...
Login successful!
Session saved to /path/to/ig-session.json
Cookies exported to /path/to/ig-cookies.txt
Docker detected. To apply the new cookies:
  docker compose restart
The container will pick up the new files on next request.
Cookies refreshed successfully.
Rebuilding and restarting bot...
...
=== Update complete ===
```

## Troubleshooting

### Login fails with IP blacklisting

Instagram rate-limits login attempts from the same IP. Solutions:

1. Wait 10-15 minutes and retry
2. Log in from your phone/browser first, then retry the script
3. Use a different network (VPN)

### Cookies work locally but not in Docker

Verify the volume mounts are correct:

```bash
docker compose exec bot cat /usr/src/app/ig-cookies.txt
```

If the file is empty or missing, check `docker-compose.yml` volume mounts.

### gallery-dl still fails after refresh

1. Check the cookies file exists and has content: `cat ig-cookies.txt`
2. Verify the session is valid: `python scripts/python/check_cookies.py`
3. Check bot logs for gallery-dl errors: `grep gallery-dl logs/request-details.jsonl | tail -5`
4. Instagram may have changed their API — check instagrapi compatibility

### Cron job not running

1. Verify crontab: `crontab -l`
2. Check cron service: `systemctl status cron` (or `crond`)
3. Check logs: `cat logs/cron.log`
4. Ensure the working directory path is absolute in the cron entry

### "instagrapi not installed" error

Install on the host (not in Docker):

```bash
pip install instagrapi python-dotenv
```

## Files Reference

| File | Location | Purpose | Gitignored |
|------|----------|---------|------------|
| `src/cookies.py` | In container | Core refresh logic | No |
| `scripts/python/ig_login_local.py` | Host + container | Standalone login script | No |
| `scripts/python/check_cookies.py` | Host + container | Staleness checker | No |
| `scripts/shell/refresh-ig-cookies.sh` | Host + container | Check → refresh orchestrator | No |
| `ig-cookies.txt` | Host root | Netscape cookies for gallery-dl | Yes |
| `ig-session.json` | Host root | instagrapi session state | Yes |

## Related

- [Project Overview](README.md) — config.py section for `IG_*` variables
- [Content Delivery](content-delivery/) — how cookies are used in downloads
