# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

########## Build Stage ##########
FROM python:${PYTHON_VERSION}-slim AS build

WORKDIR /usr/src/app

# Install system deps for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

########## Runtime Stage ##########
FROM python:${PYTHON_VERSION}-slim

# Install yt-dlp and gallery-dl via pip, ffmpeg for audio extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "yt-dlp[default,curl-cffi] @ https://github.com/yt-dlp/yt-dlp/archive/master.tar.gz" gallery-dl

# Deno JS runtime for yt-dlp YouTube extraction
COPY --from=denoland/deno:latest --chmod=755 /usr/bin/deno /usr/bin/deno

WORKDIR /usr/src/app

# Copy installed deps from build stage
COPY --from=build /install /usr/local

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
