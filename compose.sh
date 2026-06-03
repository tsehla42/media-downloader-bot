#!/usr/bin/env bash
set -euo pipefail

PROJECT=media-downloader-bot

time docker compose build --no-cache

COMPOSE_PROJECT_NAME=$PROJECT docker compose up -d
