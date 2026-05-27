import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
ALLOWED_USER_IDS = [
    int(uid) for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()
]
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/bot-downloads")
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "50"))
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))
