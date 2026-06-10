# Logging System

The bot uses structured JSON logging with three-file split for different types of events.

## Architecture

Logs are split into three files based on event type:
- `requests.jsonl` - Request lifecycle (received, completed, failed)
- `request-details.jsonl` - Intermediate download steps
- `service.jsonl` - Bot events (start/stop, chat membership, new users)

## Configuration

```bash
LOG_OUTPUT=both          # console, file, or both
LOG_DIR=logs             # Log file directory
LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR, CRITICAL
MODE=development         # development or production (affects log file name)
```

## Log Files

### requests.jsonl
Request lifecycle events. See [Request Logging](requests.md) for details.

### request-details.jsonl
Intermediate download steps (yt-dlp calls, retries, gallery-dl attempts). See [Details Logging](details.md) for details.

### service.jsonl
Bot events and service logs. See [Service Logging](service.md) for details.

## Log Format

All logs use structured JSON format:

```json
{
  "timestamp": "2026-06-10T20:41:50.042963+03:00",
  "level": "INFO",
  "message": "Request received",
  "event": "request_received",
  "request_id": "8e314411",
  "url": "https://vt.tiktok.com/ZS9Gg6dGp/",
  "platform": "tiktok",
  "user": {"id": 628055047, "name": "Меменасе", "username": "memenac"},
  "chat": {"id": -1003804964305, "name": "mememedia test", "type": "supergroup"}
}
```

## Examples

See [Log Examples](examples/) for real log samples.

## Implementation

Logging is implemented in `src/logging_config.py` using:
- Structured JSON formatter
- Filter-based routing by logger name
- Contextvars for request_id tracking
- Decorator `@with_request_logging` for automatic request lifecycle logging
