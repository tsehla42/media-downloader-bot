# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

########## Build Stage ##########
FROM python:${PYTHON_VERSION}-slim AS build

WORKDIR /usr/src/app

# Install system deps for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
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
    && pip install --no-cache-dir yt-dlp gallery-dl

WORKDIR /usr/src/app

# Copy installed deps from build stage
COPY --from=build /install /usr/local

# Copy application code
COPY src/ ./src/

# Run as non-root
RUN useradd --create-home appuser

# Create download and log directories with correct ownership
RUN mkdir -p /tmp/bot-downloads /usr/src/app/logs \
    && chown -R appuser:appuser /tmp/bot-downloads /usr/src/app/logs
USER appuser

CMD ["python", "src/bot.py"]
