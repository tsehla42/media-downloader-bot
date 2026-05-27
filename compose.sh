#!/usr/bin/env bash
set -euo pipefail

IMAGE=media-downloader-bot
PROJECT=media-downloader-bot

docker build -t "$IMAGE" .

COMPOSE_PROJECT_NAME=$PROJECT docker compose up -d
