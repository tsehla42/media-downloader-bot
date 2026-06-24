#!/usr/bin/env python3
"""Generate Instagram session files by logging in from the host machine.

Instagram blocks logins from Docker containers, so this must run on the
host (not inside Docker). The generated files are mounted into the
container via docker-compose volumes.

Usage:
    pip install instagrapi python-dotenv
    python scripts/ig_login_local.py

Reads IG_USERNAME and IG_PASSWORD from .env (project root).
Outputs: ig-cookies.txt and ig-session.json in the project root.
"""

import json
import os
import sys
import time

# Find project root (two levels up from scripts/python/)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))

from dotenv import load_dotenv
load_dotenv(os.path.join(project_root, ".env"))

# Detect Docker environment
if os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER"):
    print("ERROR: This script must run on the HOST, not inside Docker.")
    print("Instagram blocks logins from Docker containers.")
    print("Run this from your host machine instead.")
    sys.exit(1)

username = os.environ.get("IG_USERNAME", "")
password = os.environ.get("IG_PASSWORD", "")

if not username or not password:
    print("ERROR: IG_USERNAME and IG_PASSWORD must be set in .env")
    print("Add them to your .env file and try again.")
    sys.exit(1)

try:
    from instagrapi import Client
    from instagrapi.mixins.challenge import ChallengeChoice
except ImportError:
    print("ERROR: instagrapi not installed. Run: pip install instagrapi")
    sys.exit(1)


def challenge_code_handler(username, choice):
    """Prompt user for verification code during challenge flow."""
    if choice == ChallengeChoice.SMS:
        method = "SMS"
    elif choice == ChallengeChoice.EMAIL:
        method = "email"
    else:
        method = str(choice)
    print(f"\nInstagram challenge: verification code sent via {method}")
    code = input("Enter the verification code: ").strip()
    return code


cl = Client()
cl.challenge_code_handler = challenge_code_handler
print(f"Logging in as {username}...")

try:
    cl.login(username, password)
except Exception as e:
    print(f"Login failed: {e}")
    print("\nTroubleshooting:")
    print("  1. Wait 10-15 minutes and retry (rate limit)")
    print("  2. Log in from your phone/browser first, then retry")
    print("  3. Check username/password in .env")
    sys.exit(1)

print("Login successful!")

# Save session
session_path = os.path.join(project_root, "ig-session.json")
cl.dump_settings(session_path)
print(f"Session saved to {session_path}")

# Export cookies from authorization_data
cookies_path = os.path.join(project_root, "ig-cookies.txt")
settings = cl.get_settings()
auth = settings.get("authorization_data", {})
sessionid = auth.get("sessionid", "")
ds_user_id = auth.get("ds_user_id", "")

if sessionid:
    with open(cookies_path, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{sessionid}\n")
        if ds_user_id:
            f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tds_user_id\t{ds_user_id}\n")
    print(f"Cookies exported to {cookies_path}")

    # Log to service.jsonl
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    # Determine log file based on MODE env var
    mode = os.environ.get("MODE", "development")
    log_file = "service.jsonl" if mode == "production" else "service.dev.jsonl"
    log_path = os.path.join(log_dir, log_file)
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "event": "ig_cookies_refreshed",
        "message": "Instagram cookies refreshed via host login",
        "username": username,
        "ds_user_id": ds_user_id,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"Logged to {log_path}")
else:
    print("Warning: no sessionid found in authorization_data")
    sys.exit(1)

# Check if Docker is running and advise
docker_compose = os.path.join(project_root, "docker-compose.yml")
if os.path.isfile(docker_compose):
    print("\nDocker detected. To apply the new cookies:")
    print("  docker compose restart")
    print("\nThe container will pick up the new files on next request.")
