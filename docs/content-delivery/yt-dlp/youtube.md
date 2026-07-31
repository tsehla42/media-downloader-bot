# YouTube Downloads

YouTube and YouTube Music download handling.

## Supported URLs

- `youtube.com/watch?v=...`
- `youtu.be/...`
- `m.youtube.com/watch?v=...`
- `music.youtube.com/watch?v=...`

## Playlist Handling

- **Pure playlists** (`list=` without `v=`): silently skipped, logged with `skip_reason: "playlist"`
- **Single video in playlist** (`v=...&list=...`): `list=` parameter stripped, video downloaded normally

## Download Flow

1. Detect platform as `youtube` or `ytmusic`
2. Skip pure playlist URLs silently
3. Fetch metadata with `VIDEO_FORMAT_SELECTOR` (matches `download_video()`'s `best[ext=mp4]...` format) for accurate size estimate (60s timeout)
4. If age-restricted: raise `DownloadAuthRequired` → user sees "This content is restricted"
5. Check if file size > 50MB limit
6. If too large: skip with `skip_reason: "size_limit"`
7. If under limit: download best quality
8. Send to user

## Metadata Fetching

```python
# src/downloader.py
def get_metadata(url: str, format_selector: str | None = None) -> dict | None:
    """Get video metadata via yt-dlp --dump-json.

    Args:
        format_selector: Optional yt-dlp -f flag. When set, metadata reflects
            the size of the format that will actually be downloaded (important
            for YouTube where download_video() forces MP4, not bestvideo).
    """
    ytdlp = _find_ytdlp()
    try:
        cmd = [ytdlp, "--dump-json", "--no-download", "--no-playlist"]
        if format_selector:
            cmd.extend(["-f", format_selector])
        cmd.append(url)
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "Sign in to confirm your age" in stderr:
                raise DownloadAuthRequired(stderr)
            # Logs stderr to request-details.jsonl
            logger.warning("get_metadata: yt-dlp failed (code %d)", result.returncode, extra=extra)
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("get_metadata: timed out after 60s", extra=extra)
        return None
```

Key behaviors:
- **60s timeout** (up from 30s) — gives playlists and slow extractions more time
- **`--no-playlist`** — fetches metadata for single video only, ignores playlist context
- **Optional `format_selector`** — when set, passes `-f` flag to yt-dlp so metadata size reflects the format that will actually be downloaded. Used for YouTube where `download_video()` uses `best[ext=mp4]...` but default yt-dlp picks `bestvideo+bestaudio/best` (much larger).
- **Stderr logging** — failure reason logged to `request-details.jsonl` for debugging
- **Age-restriction detection** — raises `DownloadAuthRequired` for login-gated content

## Format Picker

When video is too large (>50MB), bot shows format picker:

```
Video is too large for direct download (52.3MB).
Choose format:

[Video] [Audio] [Both]
```

### Callback Handler

```python
# src/platforms/youtube.py
async def ytmusic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle format picker callback."""
    query = update.callback_query

    # Parse pipe-separated callback data: "ytm|{msg_id}|{choice}"
    _, msg_id_str, choice = query.data.split("|")
    msg_id = int(msg_id_str)

    pending = _ytmusic_pending.pop(msg_id, None)
    if not pending:
        await query.answer("Request expired. Send the link again")
        return

    await query.answer()
    url = pending["url"]

    async with typing_indicator(query.message.chat.id, context.bot):
        if choice == "audio":
            success = download_audio(url, f"{base}.mp3")
            # ... send audio
        elif choice == "video":
            video_ok = await _download_and_send_video(url, base, output_path, caption, reply_params, update.effective_message, context)
            # ... send video
        elif choice == "both":
            # Download video and audio concurrently via asyncio.to_thread
            video_task = asyncio.to_thread(download_video, url, output_path, MAX_FILE_SIZE)
            audio_task = asyncio.to_thread(download_audio, url, f"{base}.mp3")
            results = await asyncio.gather(video_task, audio_task, return_exceptions=True)
            # ... send both
```

## Audio Downloads

```python
# src/downloader.py
def download_audio(url: str, output_path: str) -> bool:
    """Extract audio as MP3."""
    ytdlp = _find_ytdlp()
    result = subprocess.run(
        [
            ytdlp,
            "--extract-audio",
            "--audio-format", "mp3",
            "-o", output_path,
            "--no-playlist",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return result.returncode == 0
```

## Error Handling

### Age-Restricted Content
- `get_metadata()` detects "Sign in to confirm your age" in stderr
- Raises `DownloadAuthRequired` → caught by `_download_and_send()`
- User sees: "This content is restricted. Login required to access"
- Logged with `skip_reason: "auth_required"`

### Metadata Fetch Failed
- Stderr logged to `request-details.jsonl` for debugging
- Logged with `skip_reason: "metadata_failed"`
- User sees: "Could not fetch post"

### Video Too Large (>50MB)
- Logged with `skip_reason: "size_limit"`
- User sees: "This video is above Telegram's 50MB limit"

### Format Not Available
- Bot tries best available format
- Falls back to `worst` if needed

## Related

- [yt-dlp Integration](README.md) - General yt-dlp docs
- [TikTok](tiktok.md) - TikTok downloads
- [Instagram](instagram.md) - Instagram downloads
