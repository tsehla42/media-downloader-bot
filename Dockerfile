# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.14

########## Build Stage ##########
FROM python:${PYTHON_VERSION}-slim AS build

WORKDIR /usr/src/app

# Install system deps for building (git: python-telegram-bot git dependency)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install locked Python deps into /usr/src/app/.venv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

########## Runtime Stage ##########
FROM python:${PYTHON_VERSION}-slim

# Install yt-dlp and gallery-dl via pip, ffmpeg for audio extraction
# yt-dlp: installed from master (not a pinned release) because scraper tools
# need fast turnaround when platforms change their APIs. Rebuilding the image
# picks up fixes within hours instead of waiting for a release. The tradeoff
# is no reproducibility, but this bot breaks when extractors go stale, so
# staying current outweighs pinning.
# gallery-dl: pinned to 1.32.4 — 1.32.9+ broke TikTok extraction. Retested
# 2026-09-26 against 1.32.13 on 4 known-failing TikTok photo URLs: 1.32.13
# failed all 4 (403) while 1.32.4 succeeded on 1 — newer is not better.
# TikTok extractor code is unchanged upstream since Feb 2026 anyway.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "yt-dlp[default,curl-cffi] @ https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz" "gallery-dl==1.32.4"

# Deno JS runtime for yt-dlp YouTube extraction
COPY --from=denoland/deno:latest --chmod=755 /usr/bin/deno /usr/bin/deno

WORKDIR /usr/src/app

# Copy locked deps (.venv) from build stage
COPY --from=build /usr/src/app/.venv /usr/src/app/.venv

# venv first on PATH: python/pytest/gallery-dl resolve to the venv,
# yt-dlp falls through to the system install above
ENV PATH="/usr/src/app/.venv/bin:$PATH"

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Run as non-root
RUN useradd --create-home appuser

# Create download, log, and cache directories with correct ownership
RUN mkdir -p /tmp/bot-downloads /usr/src/app/logs /usr/src/app/data \
    && chown -R appuser:appuser /tmp/bot-downloads /usr/src/app/logs /usr/src/app/data

# Ensure appuser can write to working directory
RUN chown appuser:appuser /usr/src/app

USER appuser

CMD ["python", "src/bot.py"]
