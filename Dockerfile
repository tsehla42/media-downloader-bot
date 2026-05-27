# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

########## Build Stage ##########
FROM python:${PYTHON_VERSION}-slim AS build

WORKDIR /usr/src/app

# Install system deps for yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

########## Runtime Stage ##########
FROM python:${PYTHON_VERSION}-slim

# Install yt-dlp via pip in runtime image
RUN pip install --no-cache-dir yt-dlp

WORKDIR /usr/src/app

# Copy installed deps from build stage
COPY --from=build /install /usr/local

# Copy application code
COPY *.py ./

# Create download directory
RUN mkdir -p /tmp/bot-downloads

# Run as non-root
RUN useradd --create-home appuser
USER appuser

CMD ["python", "bot.py"]
