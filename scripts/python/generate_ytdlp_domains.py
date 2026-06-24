#!/usr/bin/env python3
"""Fetch yt-dlp supported sites and generate a domain whitelist.

Usage:
    python scripts/generate_ytdlp_domains.py

Writes src/ytdlp_domains.py with a YTDLP_DOMAINS frozenset.
The output file is gitignored — regenerate as needed.

Strategy:
  1. If yt-dlp is installed, extract domains from each extractor's _VALID_URL pattern.
  2. Otherwise, fetch supportedsites.md from GitHub and extract domain-like site names.
"""

import re
import sys
import urllib.request
from pathlib import Path

GITHUB_URL = "https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/supportedsites.md"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "src" / "ytdlp_domains.py"

EXCLUDED_EXTENSIONS = {".php", ".html", ".aspx", ".asp", ".swf", ".jsp", ".do", ".ashx", ".clip", ".xml"}


def fetch_supported_sites() -> str:
    """Fetch supportedsites.md from GitHub."""
    req = urllib.request.Request(GITHUB_URL, headers={"User-Agent": "ytdlp-domain-gen/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _is_valid_domain(d: str) -> bool:
    """Check if a string looks like a valid domain."""
    if not d or len(d) < 2 or "." not in d:
        return False
    tld = d.split(".")[-1]
    # Mixed-case TLD indicates regex contamination (e.g. "Ptldcom")
    if tld != tld.lower():
        return False
    # Block non-domain file extensions (e.g. "api.php", "embed.html")
    for ext in EXCLUDED_EXTENSIONS:
        if d.endswith(ext):
            return False
    return (
        not d.startswith(("-", "."))
        and "(" not in d
        and ")" not in d
        and ".onion" not in d
        and "example" not in d
        and tld.isalpha()
        and 2 <= len(tld) <= 6
    )


def extract_domains_from_extractors() -> frozenset[str]:
    """Extract domains by importing yt-dlp and parsing _VALID_URL patterns."""
    try:
        from yt_dlp import list_extractors
    except ImportError:
        return frozenset()

    domains: set[str] = set()

    for ie in list_extractors():
        valid_url = getattr(ie, "_VALID_URL", "")
        if isinstance(valid_url, (list, tuple)):
            valid_url = valid_url[0] if valid_url else ""
        if not isinstance(valid_url, str) or not valid_url:
            continue

        # Remove inline flags like (?ix) at the start
        cleaned = re.sub(r"\(\?[a-z]+\)", "", valid_url)

        # Phase 1: Expand alternation groups to get individual domain variants.
        # Handle patterns like (?:(?:twitter|x)\.com) and (?:foo|bar)\.com
        # The _VALID_URL uses \. for literal dots, so we match \)\. or \)\. pattern
        for m in re.finditer(r"\(([^()]*)\)\\.([a-zA-Z]{2,})", cleaned):
            tld = m.group(2).lower()
            group_content = m.group(1)
            # Skip non-alternation groups (no | in content)
            if "|" not in group_content:
                continue
            for part in group_content.split("|"):
                part = part.strip().replace("\\", "")
                # Strip ?: non-capturing prefix
                if part.startswith("?:"):
                    part = part[2:]
                if part and re.match(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*$", part):
                    candidate = f"{part}.{tld}".lower()
                    if _is_valid_domain(candidate):
                        domains.add(candidate)

        # Phase 1b: Handle TLD alternations like pinterest\.(?:com|fr|de|...)
        # These have a base domain followed by a group of TLD alternatives.
        # Use .*? to match across newlines/whitespace in the group content.
        for m in re.finditer(
            r"([a-zA-Z0-9][a-zA-Z0-9.-]*)\\?\.\((?:\?:)?(.*?)\)",
            cleaned,
            re.DOTALL,
        ):
            base = m.group(1).lower()
            tlds_raw = m.group(2)
            if "|" in tlds_raw:
                for tld in tlds_raw.split("|"):
                    tld = tld.strip().replace("\\.", ".").replace("\\", "")
                    tld = re.sub(r"[^a-zA-Z.]", "", tld)  # strip whitespace/newlines
                    # Handle compound TLDs like co.uk, com.au
                    if tld and re.match(r"^[a-zA-Z.]{2,10}$", tld):
                        candidate = f"{base}.{tld}".lower()
                        if _is_valid_domain(candidate):
                            domains.add(candidate)

        # Phase 2: Handle optional groups like (?:media)? by removing them,
        # then extract the base domain.
        # e.g. reddit(?:media)?\.com -> reddit.com
        simplified = re.sub(r"\(\?:[^)]+\)\?", "", cleaned)

        # Phase 3: Replace character-class TLDs like \.[a-z]{2,3} with .com
        simplified = re.sub(r"\\?\.\[a-z\]\{2,6\}", ".com", simplified)

        # Phase 4: Unescape regex escapes for literal matching
        simplified = simplified.replace("\\.", ".").replace("\\-", "-")

        # Phase 5: Extract simple domain patterns
        for d in re.findall(
            r"(?:https?://)?(?:www\.)?([a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,})",
            simplified,
        ):
            d = d.lower().rstrip(".")
            if _is_valid_domain(d):
                domains.add(d)

    return frozenset(sorted(domains))


def extract_domains_from_markdown(markdown: str) -> frozenset[str]:
    """Extract domains from the markdown list.

    yt-dlp's supportedsites.md lists extractor names in bold, many of which
    are domain-like (e.g. **bbc.co.uk**, **9gag**). We extract names that
    look like valid domains (contain at least one dot and a 2-6 char TLD).
    """
    site_names = re.findall(r"\*\*([^:*]+)\*\*", markdown)
    domains: set[str] = set()
    for name in site_names:
        name = name.strip().lower()
        if _is_valid_domain(name):
            domains.add(name)
    return frozenset(sorted(domains))


def write_output(domains: frozenset[str]) -> None:
    """Write the domain set to a Python file."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    domain_lines = ",\n".join(f'    "{d}"' for d in sorted(domains))
    content = f'''"""Auto-generated yt-dlp supported domains. Do not edit manually.

Regenerate: python scripts/generate_ytdlp_domains.py

# Count: {len(domains)}
"""

YTDLP_DOMAINS: frozenset[str] = frozenset({{
{domain_lines},
}})
'''
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {len(domains)} domains to {OUTPUT_PATH}")


def main() -> None:
    # Prefer extracting from yt-dlp's own extractor metadata (much more complete)
    domains = extract_domains_from_extractors()
    source = "yt-dlp extractors"

    if not domains:
        print("yt-dlp not installed, falling back to supportedsites.md", file=sys.stderr)
        try:
            markdown = fetch_supported_sites()
        except Exception as e:
            print(f"Error fetching supportedsites.md: {e}", file=sys.stderr)
            sys.exit(1)
        domains = extract_domains_from_markdown(markdown)
        source = "supportedsites.md"

    if not domains:
        print("Error: no domains extracted", file=sys.stderr)
        sys.exit(1)

    print(f"Extracted {len(domains)} domains from {source}")
    write_output(domains)


if __name__ == "__main__":
    main()
