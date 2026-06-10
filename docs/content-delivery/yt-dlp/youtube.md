# YouTube Downloads

YouTube and YouTube Music download handling.

## Supported URLs

- `youtube.com/watch?v=...`
- `youtu.be/...`
- `m.youtube.com/watch?v=...`
- `music.youtube.com/watch?v=...`

## Download Flow

1. Detect platform as `youtube` or `ytmusic`
2. Fetch metadata (title, duration, file size)
3. Check if file size > 50MB limit
4. If too large: show format picker (video/audio/both)
5. If under limit: download best quality
6. Send to user

## Metadata Fetching

```python
# src/downloader.py
def get_metadata(url: str) -> dict | None:
    """Get video metadata via yt-dlp --dump-json."""
    try:
        ytdlp = _find_ytdlp()
        result = subprocess.run(
            [ytdlp, "--dump-json", "--no-download", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None
```

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

### Metadata Fetch Failed
- Bot tries download anyway
- If download fails, sends error

### Format Not Available
- Bot tries best available format
- Falls back to `worst` if needed

## Related

- [yt-dlp Integration](README.md) - General yt-dlp docs
- [TikTok](tiktok.md) - TikTok downloads
- [Instagram](instagram.md) - Instagram downloads
