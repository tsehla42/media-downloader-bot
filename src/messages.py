"""User-facing message constants.

All reply_text() and _text_result() strings used across the bot.
Import as: from messages import MSG_UNAUTHORIZED, MSG_LOGIN_REQUIRED, etc.
"""

# Auth
MSG_UNAUTHORIZED = "You are not authorized to use this bot"

# Platform detection
MSG_UNSUPPORTED_PLATFORM = "Unsupported platform"
MSG_NO_URL = "Please include a URL to download"
MSG_INVALID_URL = "Please send a valid URL"

# Download failures
MSG_LOGIN_REQUIRED = "This content is restricted. Login required to access"
MSG_FETCH_FAILED = "Could not fetch post. The content may be private or the URL is invalid"
MSG_SIZE_LIMIT = "This video is above Telegram's 50MB limit"
MSG_METADATA_FAILED = "Failed to fetch metadata"
MSG_DOWNLOAD_FAILED = "Download failed"

# Audio
MSG_AUDIO_USAGE = "Usage: /audio <url>"
MSG_AUDIO_FAILED = "Failed to download audio. Check the URL and try again"

# Caption
MSG_CAPTION_ENABLED = "Captions enabled. Videos will include the title"
MSG_CAPTION_DISABLED = "Captions removed. Videos will be sent without description"
MSG_CAPTION_STATUS = (
    "Current caption setting: {state}\n\n"
    "Usage:\n"
    "/caption on - Show video captions\n"
    "/caption off - Remove video captions (default)"
)

# YouTube Music
MSG_YTMUSIC_AUDIO_FAILED = "Audio download failed"
MSG_YTMUSIC_VIDEO_FAILED = "Video download failed"
MSG_YTMUSIC_UNKNOWN_CHOICE = "Unknown format choice"
MSG_YTMUSIC_REQUEST_EXPIRED = "Request expired. Send the link again"

# Start / Help
MSG_START = (
    "Media Downloader Bot\n\n"
    "Send me a YouTube, TikTok, or Instagram URL and I'll download it for you\n"
    "You can send multiple URLs in one message or send them one by one.\n"
    "Max file size: {max_file_size}MB\n\n"
    "Commands:\n"
    "/help - Show supported platforms and commands\n"
    "/audio <url> - Download as audio (MP3)\n"
    "/caption on|off - Toggle video captions"
)
MSG_HELP = (
    "Supported platforms:\n"
    "- YouTube (videos, shorts)\n"
    "- TikTok (videos, no watermark)\n"
    "- Instagram (reels, posts, carousels)\n\n"
    "Commands:\n"
    "/audio <url> - Download as audio (MP3)\n"
    "/caption on - Show video captions\n"
    "/caption off - Remove video captions (default)\n\n"
    "Max file size: {max_file_size}MB\n"
    "You can send multiple URLs in one message."
)

# Group admin
MSG_ONLY_ADMINS_CAN_ADD = "Only bot admins can add me to groups"

# Guest mode
MSG_GUEST_DOWNLOAD_FAILED = "Download failed: {error}"
MSG_GUEST_NO_IMAGES = "No images found"
MSG_GUEST_METADATA_FAILED = "Could not fetch video metadata"
MSG_GUEST_UPLOAD_FAILED = "Failed to upload video to Telegram"
MSG_GUEST_DOWNLOAD_NOT_FOUND = "Downloaded file not found"
MSG_GUEST_COULD_NOT_DOWNLOAD = "Could not download media from this URL"
MSG_GUEST_CONTENT_NOT_FOUND = "Unsupported platform or content not found"
