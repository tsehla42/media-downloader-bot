"""Platform-specific yt-dlp constants.

Centralizes User-Agent, referer headers, and common flags used across
download functions.
"""

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

# Flags shared by every yt-dlp subprocess call.
COMMON_YTDL_ARGS = [
    "--no-playlist",
    "--user-agent", USER_AGENT,
]

# --- TikTok ---

TIKTOK_REFERER = "https://www.tiktok.com/"
