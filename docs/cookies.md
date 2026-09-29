# Cookie System

The bot supports cookies for Instagram, TikTok, and YouTube to enable authenticated downloads.

**Cookies are renewed manually only.** Automated renewal (staleness checks, cron jobs,
refresh-on-update) was removed — it never worked reliably. When auth-gated downloads
start failing, export fresh cookies from a browser and upload them through the bot
(see below).

## Uploading cookies via the bot

A bot admin can update cookie files by sending a `.txt` document directly to the
bot in a **private chat** (P2P). Group chats, guest mode, and inline queries are
ignored.

1. Export cookies from a browser as Netscape format (`cookies.txt`-style export)
2. Send the file to the bot with the caption:

   ```
   cookie update <platform>
   ```

   - `cookie update` is case-insensitive (`Cookie Update` works)
   - `<platform>` must be lowercase: `tt`, `ig`, or `yt`
   - Anything else → `Invalid caption`; no caption → `Caption cannot be empty`

3. On success the bot replies `Cookies updated for <platform>` and the file is saved as:
   - Dated copy: `cookies/<platform>-cookie-<YYYY-MM-DD>.txt` (history; same-day
     re-upload overwrites)
   - Active copy: the path the downloader reads (`tiktok-cookies.txt`,
     `ig-cookies.txt`, or `yt-cookies.txt`)

Validation: only bot admins are accepted — any document from a non-admin (with or
without caption) and any document in a group chat is silently ignored. Files must
end in `.txt` and contain Netscape-format cookies; anything else → `Invalid file`.

Each successful update logs a `cookies_updated` event to `service.jsonl` with the
platform, filename, and the admin who uploaded it.

The `cookies/` directory is mounted into the container (`./cookies:/usr/src/app/cookies`),
so uploads persist across container rebuilds.

## Instagram Cookies

Instagram image downloads via gallery-dl require authentication cookies. Cookies are
exported from a browser and delivered to the bot via the upload flow above
(`cookie update ig`), or placed on disk manually.

### Setup

1. Log into Instagram in a desktop browser (Chrome, Firefox, etc.)
2. Install a cookies-export extension such as "Get cookies.txt LOCALLY"
3. Export cookies for `instagram.com` as Netscape format
4. Either:
   - Send the file to the bot with caption `cookie update ig`, or
   - Place it as `ig-cookies.txt` in the project root (`IG_COOKIES_PATH` in `.env`)

   The file is bind-mounted into the container — no rebuild or restart needed.

### How long do they work?

Instagram invalidates sessions server-side (`login_required`) on suspicious
activity, password changes, or prolonged inactivity — regardless of what the
file looks like. Assume **a few weeks** and re-export when login-gated posts
fail with 403/login errors in `request-details.jsonl` while public posts still
work.

## TikTok Cookies

TikTok requires authentication for age-restricted and login-gated content.
TikTok cookies are manually exported from a browser and refreshed periodically.

### Setup

1. Log into TikTok in a desktop browser (Chrome, Firefox, etc.)
2. Install "Get cookies.txt LOCALLY" extension ([Chrome](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc))
3. Export cookies for `tiktok.com` as Netscape format
4. Place file as `tiktok-cookies.txt` in project root
5. Set `TIKTOK_COOKIES_PATH=tiktok-cookies.txt` in `.env` (optional, default is correct)
6. Restart the container so the volume mount re-reads the file:

   ```bash
   docker compose restart
   ```

### How It Works

- `get_metadata()` receives `cookies=TIKTOK_COOKIES_PATH` for TikTok URLs
- `download_video()` receives `--cookies` flag when `platform="tiktok"`
- `download_gallery_dl_images()` receives `--cookies` for TikTok photo posts
  (gallery-dl accepts the same Netscape file)
- Cookie file is mounted as a **writable** volume (yt-dlp writes the jar back,
  sliding some expiry dates forward on successful requests)

### Cookie Expiration

The `Expires` dates in an exported file are only the **client-side maximum
lifetimes** TikTok chose when issuing the cookies (e.g. `sessionid` ≈ 6 months,
`sid_guard` ≈ 1 year, `ttwid` = 1 year per TikTok's cookie policy). The server
can invalidate any of them earlier — logout elsewhere, password change, new IP,
inactivity, or automation detection — regardless of the dates in the file.

Practical rule: **assume ~30 days** and re-export from the browser when TikTok
downloads start failing with auth/permission errors
(`Log in for access`, `You do not have permission`). Failing with
`Unexpected response` / `IP address is blocked` / `403` means TikTok-side
blocking, not expired cookies — re-exporting will not help those.

### Volume mount

The container picks up the file via volume mount in `docker-compose.yml`:

```yaml
volumes:
  - ./tiktok-cookies.txt:/usr/src/app/tiktok-cookies.txt
```

Note: TikTok cookies are mounted as **writable** (not `:ro`) because yt-dlp
writes back to update cookies. Instagram cookies are also mounted writable so
the bot can replace them via cookie upload. YouTube cookies and dated backups
live in the `./cookies/` directory mount (`./cookies:/usr/src/app/cookies`).

## YouTube Cookies

YouTube cookies unlock age-restricted and login-gated videos. The simplest way
to set them is the bot upload flow above (`cookie update yt`), or place the file
manually at `yt-cookies.txt` in the project root (`YT_COOKIES_PATH` in `.env`).

### How It Works

- `get_metadata()` falls back to `YT_COOKIES_PATH` for YouTube URLs when no
  explicit cookies param is given
- `download_video()` and `download_audio()` pass `--cookies` for YouTube URLs
  when the file exists
- The file is bind-mounted into the container (`./yt-cookies.txt:/usr/src/app/yt-cookies.txt`)
  — no restart needed

If the file is absent, everything works as before (no `--cookies` flag).

## Troubleshooting

### Cookies work locally but not in Docker

Verify the volume mounts are correct:

```bash
docker compose exec bot cat /usr/src/app/ig-cookies.txt
```

If the file is empty or missing, check `docker-compose.yml` volume mounts.

### gallery-dl still fails after cookie update

1. Check the cookies file exists and has content: `cat ig-cookies.txt`
   (an empty 0-byte file means the upload/export failed)
2. Check bot logs for gallery-dl errors: `grep gallery-dl logs/request-details.jsonl | tail -5`
3. Re-export fresh cookies from the browser — Instagram invalidates sessions
   server-side regardless of the file contents

## Files Reference

| File | Location | Purpose | Gitignored |
|------|----------|---------|------------|
| `ig-cookies.txt` | Host root | Active Netscape cookies for gallery-dl (Instagram) | Yes |
| `tiktok-cookies.txt` | Host root | Active Netscape cookies for yt-dlp + gallery-dl (TikTok) | Yes |
| `yt-cookies.txt` | Host root | Active Netscape cookies for yt-dlp (YouTube) | Yes |
| `cookies/<platform>-cookie-<date>.txt` | Host `cookies/` | Dated backups from bot uploads | Yes |

## Related

- [Project Overview](README.md) — config.py section for `IG_*` variables
- [Content Delivery](content-delivery/) — how cookies are used in downloads
