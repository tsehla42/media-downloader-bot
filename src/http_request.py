"""Resilient HTTP request layer for the Telegram Bot API.

Media uploads stream to Telegram in 64KB chunks. If the connection stalls
mid-upload, PTB raises ``TimedOut`` with an ``httpx.WriteTimeout`` cause.
A write timeout means the request body never fully reached Telegram, so the
Bot API cannot have processed it — retrying once on a fresh connection is
safe and cannot duplicate a send. Read timeouts are *not* retried: the
request may already have been processed when the response was lost.
"""

import httpx
from telegram.error import TimedOut
from telegram.request import BaseRequest, HTTPXRequest

# Total attempts for a stalled upload: the original plus one retry
UPLOAD_ATTEMPTS = 2

# PTB's default media write timeout is 20s — too tight for large videos on a
# slow or jittery uplink. A stalled upload of up to 120s is tolerated before
# the retry logic kicks in.
MEDIA_WRITE_TIMEOUT = 120.0


def _rewind_uploads(request_data) -> bool:
    """Seek upload file handles back to the start so a retry re-sends the full file.

    Returns False if any handle cannot be rewound (retrying then would upload a
    truncated file, so the caller must not retry).
    """
    if request_data is None:
        return True
    for value in request_data.multipart_data.values():
        content = value[1] if isinstance(value, tuple) else value
        if hasattr(content, "seek"):
            try:
                content.seek(0)
            except (OSError, ValueError):
                # io.UnsupportedOperation subclasses both OSError and ValueError
                return False
    return True


class ResilientHTTPXRequest(HTTPXRequest):
    """HTTPXRequest that retries once when an upload's write to Telegram stalls."""

    async def do_request(
        self,
        url: str,
        method: str,
        request_data=None,
        read_timeout=BaseRequest.DEFAULT_NONE,
        write_timeout=BaseRequest.DEFAULT_NONE,
        connect_timeout=BaseRequest.DEFAULT_NONE,
        pool_timeout=BaseRequest.DEFAULT_NONE,
    ) -> tuple[int, bytes]:
        for attempt in range(UPLOAD_ATTEMPTS):
            try:
                return await super().do_request(
                    url=url,
                    method=method,
                    request_data=request_data,
                    read_timeout=read_timeout,
                    write_timeout=write_timeout,
                    connect_timeout=connect_timeout,
                    pool_timeout=pool_timeout,
                )
            except TimedOut as exc:
                write_stalled = isinstance(exc.__cause__, httpx.WriteTimeout)
                if (
                    attempt + 1 >= UPLOAD_ATTEMPTS
                    or not write_stalled
                    or not _rewind_uploads(request_data)
                ):
                    raise
        raise AssertionError("unreachable")  # pragma: no cover
