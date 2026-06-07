import json
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


def _load_allowed_user_ids() -> tuple[set[int], bool]:
    """Load allowed user IDs from JSON file + env var, merge both.

    Returns:
        Tuple of (set of IDs, whether any ID source was configured)
    """
    ids = set()
    configured = False

    # JSON file (new structure: array of objects with "id" field)
    json_path = os.path.join(os.path.dirname(__file__), "..", "allowed-contacts.json")
    if os.path.isfile(json_path):
        configured = True
        try:
            with open(json_path) as f:
                contacts = json.load(f)
            # Support both old format (dict with "allowed_user_ids") and new (array of objects)
            if isinstance(contacts, list):
                ids.update(c["id"] for c in contacts if "id" in c)
            elif isinstance(contacts, dict):
                ids.update(int(uid) for uid in contacts.get("allowed_user_ids", []))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Warning: Failed to load allowed-contacts.json: {e}")

    # Env var (comma-separated)
    env_ids = os.environ.get("ALLOWED_USER_IDS", "")
    if env_ids:
        configured = True
        ids.update(int(uid) for uid in env_ids.split(",") if uid.strip())

    return ids, configured


def _load_bot_admin_ids() -> set[int]:
    """Load bot admin IDs from env var."""
    admin_ids = os.environ.get("BOT_ADMIN_IDS", "")
    if not admin_ids:
        return set()
    try:
        return {int(uid) for uid in admin_ids.split(",") if uid.strip()}
    except ValueError as e:
        print(f"Warning: Failed to parse BOT_ADMIN_IDS: {e}")
        return set()


ALLOWED_USER_IDS, ALLOWED_IDS_CONFIGURED = _load_allowed_user_ids()
BOT_ADMIN_IDS = _load_bot_admin_ids()
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
