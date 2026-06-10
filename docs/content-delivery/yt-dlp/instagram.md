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
async def handle_instagram(update, context, url: str) -> bool:
    """Handle Instagram URL: try video download first, fallback to images."""
    reply_params = {"message_id": update.message.message_id}

    # Try video download first
    success = download_video(url, output_path, MAX_FILE_SIZE)
    if success:
        # Find downloaded file and send as video
        # ...
        return True

    # Fallback: try images with gallery-dl (uses INSTAGRAM_COOKIES)
    images = download_gallery_dl_images(url, out_dir, INSTAGRAM_COOKIES)
    if images:
        await send_images(update.message, images, reply_params)
        return True

    return False
```

## gallery-dl for Images

Instagram posts often contain multiple images. gallery-dl handles these better.

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

## Image Batching

Multiple images are sent as a media group (up to 10 per group).

```python
# src/telegram_utils.py
async def send_images(message, images: list[str], reply_params: dict) -> int:
    """Send images to Telegram, handling single photo vs media group batching."""
    total_size = 0

    if len(images) == 1:
        with open(images[0], "rb") as f:
            await message.reply_photo(photo=f, reply_parameters=reply_params)
        if os.path.isfile(images[0]):
            total_size = os.path.getsize(images[0])
    else:
        for i in range(0, len(images), 10):
            batch = images[i:i+10]
            handles = [open(img, "rb") for img in batch]
            try:
                media = [InputMediaPhoto(h) for h in handles]
                await message.reply_media_group(media=media, reply_parameters=reply_params)
            finally:
                for h in handles:
                    h.close()
        for img in images:
            if os.path.isfile(img):
                total_size += os.path.getsize(img)

    return total_size
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
