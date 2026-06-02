import json
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


def _load_allowed_user_ids() -> list[int]:
    """Load allowed user IDs from allowed_contacts.json, fallback to env var."""
    json_path = os.path.join(os.path.dirname(__file__), "..", "allowed_contacts.json")
    if os.path.isfile(json_path):
        with open(json_path) as f:
            data = json.load(f)
        return [int(uid) for uid in data.get("allowed_user_ids", [])]
    return [
        int(uid) for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()
    ]


ALLOWED_USER_IDS = _load_allowed_user_ids()
ALLOWED_GROUP_IDS = [
    int(gid) for gid in os.environ.get("ALLOWED_GROUP_IDS", "").split(",") if gid.strip()
]
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/bot-downloads")
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "50"))
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", "3"))

INSTAGRAM_COOKIES = os.environ.get("INSTAGRAM_COOKIES", "")

MODE = os.environ.get("MODE", "development")
LOG_OUTPUT = os.environ.get("LOG_OUTPUT", "both")
LOG_DIR = os.environ.get("LOG_DIR", "logs")

SEEN_USERS_FILE = os.environ.get("SEEN_USERS_FILE", "seen_users.json")
