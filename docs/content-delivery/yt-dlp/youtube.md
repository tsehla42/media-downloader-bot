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
# src/platforms/youtube.py
async def get_metadata(url: str) -> dict:
    """Fetch video metadata without downloading."""
    cmd = [
        "yt-dlp",
        "--no-download",
        "--print-json",
        url
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, await proc.communicate()
    
    return json.loads(stdout.decode())
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
    await query.answer()
    
    if query.data == "video":
        # Download video only
        await download_video(url, context)
    elif query.data == "audio":
        # Download audio only
        await download_audio(url, context)
    elif query.data == "both":
        # Download both
        await download_video(url, context)
        await download_audio(url, context)
```

## Audio Downloads

```python
# src/downloader.py
async def download_audio(url: str, request_id: str) -> str:
    """Download audio using yt-dlp."""
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--no-check-certificates",
        "-f", "bestaudio/best",
        "--extract-audio",
        "--audio-format", "mp3",
        "-o", f"{DOWNLOAD_DIR}/%(id)s.%(ext)s",
        url
    ]
    # ...
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
