# Instagram Downloads

Instagram image and video download handling.

## Supported URLs

- `instagram.com/p/...`
- `instagram.com/reel/...`
- `instagr.am/p/...`

## Download Flow

1. Detect platform as `instagram`
2. Try yt-dlp first
3. If fails, try gallery-dl with cookies
4. Send to user

## Authentication

Instagram often requires authentication for downloads.

### Cookies File

```bash
INSTAGRAM_COOKIES=/path/to/cookies.txt
```

- Use `instaloader` or browser extension to export cookies
- Place in project root or mounted volume

### gallery-dl with Cookies

```python
# src/platforms/instagram.py
async def handle_instagram(update: Update, url: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle Instagram downloads."""
    try:
        # Try yt-dlp first
        file_path = await download_video(url, request_id)
        await context.bot.send_video(chat_id=update.effective_chat.id, video=open(file_path, 'rb'))
    except Exception as e:
        # Try gallery-dl with cookies
        file_path = await download_gallery_dl_images(url, request_id)
        if file_path:
            await send_images(update, [file_path])
        else:
            await update.message.reply_text("Failed to download Instagram content")
```

## gallery-dl for Images

Instagram posts often contain multiple images. gallery-dl handles these better.

```python
# src/downloader.py
async def download_gallery_dl_images(url: str, request_id: str) -> list:
    """Download images using gallery-dl."""
    cmd = [
        "gallery-dl",
        "-d", DOWNLOAD_DIR,
        "--cookies", INSTAGRAM_COOKIES,
        url
    ]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    
    if proc.returncode == 0:
        return find_downloaded_images(url)
    return []
```

## Image Batching

Multiple images are sent as a media group (up to 10 per group).

```python
# src/telegram_utils.py
async def send_images(message, images: list, reply_params: dict):
    """Send images as media group."""
    if len(images) == 1:
        await message.reply_photo(photo=open(images[0], 'rb'), **reply_params)
    else:
        # Send as media group
        media = [InputMediaPhoto(open(img, 'rb')) for img in images[:10]]
        await message.reply_media_group(media=media, **reply_params)
```

## Error Handling

### Authentication Required
- Check if `INSTAGRAM_COOKIES` is set
- If not, send error message

### Download Failed
- Try alternative method (yt-dlp → gallery-dl or vice versa)
- If both fail, send error

## Related

- [yt-dlp Integration](README.md) - General yt-dlp docs
- [gallery-dl](../gallery-dl/) - Image downloads
