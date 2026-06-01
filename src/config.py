import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ALLOWED_USER_IDS = [
    int(uid) for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()
]
ALLOWED_GROUP_IDS = [
    int(gid) for gid in os.environ.get("ALLOWED_GROUP_IDS", "").split(",") if gid.strip()
]
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/bot-downloads")
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "50"))
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))

INSTAGRAM_COOKIES = os.environ.get("INSTAGRAM_COOKIES", "")

LOG_OUTPUT = os.environ.get("LOG_OUTPUT", "stdout")
LOG_DIR = os.environ.get("LOG_DIR", "logs")
