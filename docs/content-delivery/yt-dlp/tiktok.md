# TikTok Downloads

TikTok video download handling.

## Supported URLs

- `tiktok.com/@user/video/...`
- `vm.tiktok.com/...`
- `tiktok.com/t/...`

## Download Flow

1. Detect platform as `tiktok`
2. Download video using yt-dlp
3. If download fails, try gallery-dl fallback
4. If fallback succeeds, check for watermark
5. Send to user

## Primary Download

```python
# src/platforms/tiktok.py
async def handle_tiktok(update: Update, url: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle TikTok downloads."""
    try:
        file_path = await download_video(url, request_id)
        await context.bot.send_video(chat_id=update.effective_chat.id, video=open(file_path, 'rb'))
    except Exception as e:
        # Try gallery-dl fallback
        file_path = await handle_gallery_dl_fallback(url, request_id)
        if file_path:
            await context.bot.send_video(chat_id=update.effective_chat.id, video=open(file_path, 'rb'))
        else:
            await update.message.reply_text("Failed to download TikTok video")
```

## gallery-dl Fallback

TikTok videos often have watermarks when downloaded via yt-dlp. gallery-dl can sometimes get cleaner versions.

```python
# src/platforms/tiktok.py
async def handle_gallery_dl_fallback(url: str, request_id: str) -> str:
    """Try gallery-dl as fallback."""
    cmd = [
        "gallery-dl",
        "-d", DOWNLOAD_DIR,
        url
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    
    if proc.returncode == 0:
        # Find downloaded file
        return find_downloaded_file(url)
    return None
```

## Watermark Issue

Some TikTok videos have watermarks even after download. This is a known issue with yt-dlp.

**Workaround:** gallery-dl sometimes gets cleaner versions, but not always.

**Status:** No perfect solution yet. See todo.md for updates.

## Error Handling

### Download Failed
- Try gallery-dl fallback
- If fallback fails, send error

### Watermark Present
- Current limitation
- Document in troubleshooting

## Related

- [yt-dlp Integration](README.md) - General yt-dlp docs
- [gallery-dl Fallback](../gallery-dl/fallback-strategy.md) - Fallback logic
