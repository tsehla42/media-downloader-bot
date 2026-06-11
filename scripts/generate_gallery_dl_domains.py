#!/usr/bin/env python3
"""Fetch gallery-dl supported sites and generate a domain whitelist.

Usage:
    python scripts/generate_gallery_dl_domains.py

Writes src/gallery_dl_domains.py with a GALLERY_DL_DOMAINS frozenset.
The output file is gitignored — regenerate as needed.
"""

import re
import sys
import urllib.request
from pathlib import Path

CODEBERG_URL = "https://codeberg.org/mikf/gallery-dl/raw/branch/master/docs/supportedsites.md"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "src" / "gallery_dl_domains.py"


def fetch_supported_sites() -> str:
    """Fetch supportedsites.md from Codeberg."""
    req = urllib.request.Request(CODEBERG_URL, headers={"User-Agent": "gallery-dl-domain-gen/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def extract_domains(markdown: str) -> frozenset[str]:
    """Extract domains from the markdown table's URL column."""
    # Match URLs in the table: | Site | URL | ...
    urls = re.findall(r"https?://([a-zA-Z0-9.-]+)/", markdown)
    domains = set()
    for d in urls:
        d = re.sub(r"^www\.", "", d.lower())
        if d:
            domains.add(d)
    return frozenset(sorted(domains))


def write_output(domains: frozenset[str]) -> None:
    """Write the domain set to a Python file."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    domain_lines = ",\n".join(f'    "{d}"' for d in sorted(domains))
    content = f'''"""Auto-generated gallery-dl supported domains. Do not edit manually.

Regenerate: python scripts/generate_gallery_dl_domains.py

# Count: {len(domains)}
"""

GALLERY_DL_DOMAINS: frozenset[str] = frozenset({{
{domain_lines},
}})
'''
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {len(domains)} domains to {OUTPUT_PATH}")


def main() -> None:
    try:
        markdown = fetch_supported_sites()
    except Exception as e:
        print(f"Error fetching supportedsites.md: {e}", file=sys.stderr)
        sys.exit(1)

    domains = extract_domains(markdown)
    if not domains:
        print("Error: no domains extracted", file=sys.stderr)
        sys.exit(1)

    write_output(domains)


if __name__ == "__main__":
    main()
