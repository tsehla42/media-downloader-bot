import json
import logging
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Custom formatter that outputs JSON."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }

        # Include extra_data if present
        extra = getattr(record, "extra_data", {})
        log_data.update(extra)

        return json.dumps(log_data)
