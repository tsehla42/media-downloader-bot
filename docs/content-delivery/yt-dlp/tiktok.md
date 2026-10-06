# TikTok Downloads

TikTok video download handling.

## Supported URLs

- `tiktok.com/@user/video/...`
- `vm.tiktok.com/...`
- `tiktok.com/t/...`

## Download Flow

1. Detect platform as `tiktok`
2. **Photo-post extractor first**: `download_tiktok_photo_images()` — yt-dlp's TikTok extractor does not match `/photo/` URLs at all, so the bot resolves the URL (following `vt.`/`vm.` short links; retries transient timeouts — 3× HEAD with backoff, then a streaming GET — so a network hiccup can't misclassify a photo post as a video), rewrites `/photo/` → `/video/`, and runs `yt-dlp --write-pages` to capture the page's `__UNIVERSAL_DATA_FOR_REHYDRATION__` JSON, which contains the `imagePost` gallery URLs. The images are then downloaded directly (with cookies).
   - Non-photo URLs return `[]` immediately — the regular flow continues
   - Known photo post where extraction fails → gallery-dl safety net → if that also fails, raises `DownloadError(MSG_IMAGE_POST_FETCH_FAILED)` ("Could not fetch this image post")
3. For non-photo URLs: fetch metadata via `get_metadata()` with `--referer` (WAF bypass) and `--cookies` (auth) to check file extension
4. If metadata indicates photo post (ext in jpg/jpeg/png/webp): try gallery-dl images first (with cookies)
5. If not a photo post (or gallery-dl fails): try yt-dlp video download via `_run_ytdlp()` (with cookies)
6. If video download fails: fallback to gallery-dl images (with cookies)
7. Send to user

The referer header (`https://www.tiktok.com/`) is defined in `src/platform_args.py` as `TIKTOK_REFERER` and applied to all TikTok yt-dlp calls. This bypasses TikTok's Akamai WAF challenge.

### Why the photo-post extractor exists

gallery-dl's TikTok extractor has been blocked by TikTok's anti-bot (403 on the rehydration request after its JS challenge) since ~September 2026, and yt-dlp has never supported `/photo/` URLs or `imagePost` galleries. yt-dlp's own challenge-cookie page fetch still works, so the bot uses `--write-pages` to capture that page and parses the gallery URLs out of it. gallery-dl is kept only as a safety net.

## TikTok Cookies

TikTok requires authentication for age-restricted and login-gated content. The bot supports browser-exported Netscape cookies (`tiktok-cookies.txt`) passed to yt-dlp and gallery-dl.

### Setup

1. Log into TikTok in a desktop browser (Chrome, Firefox, etc.)
2. Install "Get cookies.txt LOCALLY" extension
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

## Four-Stage Process

```python
# src/platforms/tiktok.py
async def handle_tiktok(update, context, url: str) -> bool:
    """Handle TikTok URL: photo-post extractor first, then video, then gallery-dl."""
    reply_params = {"message_id": update.message.message_id, "allow_sending_without_reply": True}

    # Stage 1: Photo-post extractor (yt-dlp --write-pages rehydration dump)
    # Non-photo URLs return [] and fall through; known photo posts that
    # cannot be extracted raise DownloadError(MSG_IMAGE_POST_FETCH_FAILED).
    images = download_tiktok_photo_images(url, out_dir, TIKTOK_COOKIES_PATH)
    if images:
        await send_images(update.message, images, reply_params)
        return True

    # Stage 2: Check metadata for photo posts (with cookies)
    metadata = get_metadata(url, referer=TIKTOK_REFERER, cookies=TIKTOK_COOKIES_PATH)
    if metadata:
        ext = (metadata.get("ext") or "").lower()
        if ext in IMAGE_EXTENSIONS:  # {"jpg", "jpeg", "png", "webp"}
            images = download_gallery_dl_images(url, out_dir, TIKTOK_COOKIES_PATH)
            if images:
                await send_images(update.message, images, reply_params)
                return True

    # Stage 3: Try video download via yt-dlp (with cookies)
    success = download_video(url, output_path, MAX_FILE_SIZE, platform="tiktok")
    if success:
        # Find downloaded file and send as video
        # ...
        return True

    # Stage 4: Fallback to gallery-dl for images (with cookies)
    images = download_gallery_dl_images(url, out_dir, TIKTOK_COOKIES_PATH)
    if images:
        await send_images(update.message, images, reply_params)
        return True

    return False
```

## gallery-dl Fallback

TikTok videos often have watermarks when downloaded via yt-dlp. gallery-dl can sometimes get cleaner versions. For photo posts, gallery-dl is the primary tool.

```python
# src/downloader.py
def download_gallery_dl_images(url: str, output_dir: str, cookies: str = "") -> list[str]:
    """Download images using gallery-dl."""
    gd_path = _find_gallery_dl()
    if not gd_path:
        return []

    os.makedirs(output_dir, exist_ok=True)
    output_dir = os.path.abspath(output_dir)

    cmd = [gd_path, "-d", output_dir]
    if cookies:
        cookies = os.path.abspath(cookies)
        if not os.path.isfile(cookies):
            return []
        cmd.extend(["--cookies", cookies])
    cmd.append(url)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    if result.returncode != 0:
        return []

    images = sorted(
        glob.glob(f"{output_dir}/**/*.jpg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.jpeg", recursive=True)
        + glob.glob(f"{output_dir}/**/*.png", recursive=True)
        + glob.glob(f"{output_dir}/**/*.webp", recursive=True)
    )
    return images
```

## Watermark Issue

TikTok serves two types of video formats: `play_addr` (clean, no watermark) and `download_addr` (watermarked). When yt-dlp's first download attempt fails (e.g. file too large), the fallback retries with `worst[filesize<50MB]/worst` instead of bare `worst`. This prefers a filesize-constrained clean format before falling back to potentially watermarked versions.

**Known limitation:** TikTok's API is inconsistent per region — some requests only return one format, and whether it's watermarked varies. See [yt-dlp#15690](https://github.com/yt-dlp/yt-dlp/issues/15690).

## Error Handling

### Age-Restricted / Login-Required Content
Some TikTok videos are gated behind "This post may not be comfortable for some audiences. Log in for access." When yt-dlp reports this error, `download_video()` raises `DownloadAuthRequired` (custom exception). The orchestrator (`_download_and_send` for P2P/groups, `_download_media_result` for guest mode) catches it and shows: "This video has restricted access that requires login".

- **P2P chat**: message shown
- **Group chat (normal URL)**: silently ignored
- **Group chat (reply-to-retry)**: message shown
- **Guest mode**: message shown via `answer_guest_query()`

With TikTok cookies configured, age-restricted content can be downloaded directly.

### Image Post Extraction Failed
When the URL is a known photo post (`/photo/` in the URL, or a short link resolving to one) and both the page-dump extraction and the gallery-dl safety net fail, `download_tiktok_photo_images()` raises `DownloadError(MSG_IMAGE_POST_FETCH_FAILED)`. Both P2P/groups (`_download_and_send`) and guest mode (`handle_guest`) reply with its text: **"Could not fetch this image post"** (the technical yt-dlp stderr goes to `request-details.jsonl` via `raw_error`). This also fails fast (~10s) instead of attempting the yt-dlp video path, which can never work on `/photo/` URLs.

### Download Failed
- Try gallery-dl fallback
- If fallback fails, send error

### Watermark Present
- Current limitation
- Document in troubleshooting

## Related

- [yt-dlp Integration](README.md) - General yt-dlp docs
- [gallery-dl Fallback](../gallery-dl/fallback-strategy.md) - Fallback logic
- [Cookies](../../cookies.md) - TikTok and Instagram cookie setup
