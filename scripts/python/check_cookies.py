#!/usr/bin/env python3
"""Check if Instagram cookies are stale.

Useful for host-side cron jobs:
  0 9 */7 * * cd /path/to/project && python scripts/check_cookies.py || python scripts/ig_login_local.py

Exit codes:
    0 — cookies are fresh
    1 — cookies are stale or missing
    2 — error
"""

import os
import sys
import time

project_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
cookies_path = os.path.join(project_root, "ig-cookies.txt")
MAX_AGE_DAYS = 7


def main():
    if not os.path.isfile(cookies_path):
        print(f"Missing: {cookies_path}")
        sys.exit(1)

    mtime = os.path.getmtime(cookies_path)
    age_days = (time.time() - mtime) / 86400

    if age_days > MAX_AGE_DAYS:
        print(f"Stale: {age_days:.1f} days old (max {MAX_AGE_DAYS})")
        sys.exit(1)
    else:
        print(f"Fresh: {age_days:.1f} days old (max {MAX_AGE_DAYS})")
        sys.exit(0)


if __name__ == "__main__":
    main()
