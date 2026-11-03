"""Tests for the resilient HTTP request layer (upload write-timeout retry)."""

import io

import httpx
import pytest
from unittest.mock import patch

from telegram.error import TimedOut
from telegram.request import HTTPXRequest

from http_request import ResilientHTTPXRequest


class FakeRequestData:
    """Minimal stand-in for telegram.request.RequestData (only multipart_data is used)."""

    def __init__(self, multipart_data=None):
        self.multipart_data = multipart_data or {}
        self.contains_files = bool(self.multipart_data)


def _write_timeout_error():
    """A TimedOut whose cause is an httpx write timeout (upload stalled mid-body)."""
    exc = TimedOut()
    raise exc from httpx.WriteTimeout("write stalled")


@pytest.mark.asyncio
async def test_write_timeout_during_upload_is_retried_once_with_file_rewound():
    """A mid-upload WriteTimeout is retried once; the file handle is rewound so the
    second attempt re-sends the full content (the first attempt consumed it)."""
    payload = b"video-bytes" * 1024
    handle = io.BytesIO(payload)
    request_data = FakeRequestData({"video": ("clip.mp4", handle, "video/mp4")})
    reads = []
    calls = {"n": 0}

    async def flaky_do_request(self, url, method, request_data=None, **kwargs):
        calls["n"] += 1
        reads.append(request_data.multipart_data["video"][1].read())
        if calls["n"] == 1:
            _write_timeout_error()
        return 200, b"{}"

    with patch.object(HTTPXRequest, "do_request", flaky_do_request):
        result = await ResilientHTTPXRequest().do_request(
            url="https://api.telegram.org", method="POST", request_data=request_data
        )

    assert result == (200, b"{}")
    assert calls["n"] == 2
    # Both attempts must see the complete file — proves the rewind happened
    assert reads == [payload, payload]


@pytest.mark.asyncio
async def test_write_timeout_twice_raises_after_single_retry():
    """Two consecutive write timeouts: exactly two attempts, then TimedOut propagates."""
    calls = {"n": 0}

    async def always_stall(self, url, method, request_data=None, **kwargs):
        calls["n"] += 1
        _write_timeout_error()

    with patch.object(HTTPXRequest, "do_request", always_stall):
        with pytest.raises(TimedOut):
            await ResilientHTTPXRequest().do_request(
                url="https://api.telegram.org",
                method="POST",
                request_data=FakeRequestData(
                    {"video": ("clip.mp4", io.BytesIO(b"data"), "video/mp4")}
                ),
            )

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_read_timeout_is_not_retried():
    """A ReadTimeout means the request may already have been processed — no retry."""
    calls = {"n": 0}

    async def read_stall(self, url, method, request_data=None, **kwargs):
        calls["n"] += 1
        exc = TimedOut()
        raise exc from httpx.ReadTimeout("read stalled")

    with patch.object(HTTPXRequest, "do_request", read_stall):
        with pytest.raises(TimedOut):
            await ResilientHTTPXRequest().do_request(
                url="https://api.telegram.org", method="POST", request_data=None
            )

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_unrewindable_upload_is_not_retried():
    """If the file handle cannot be rewound, retrying would upload a truncated file —
    so the original TimedOut propagates instead."""
    calls = {"n": 0}

    class Unrewindable(io.RawIOBase):
        def read(self, size=-1):
            return b"data"

        def seek(self, offset, whence=0):
            raise io.UnsupportedOperation("not seekable")

    async def always_stall(self, url, method, request_data=None, **kwargs):
        calls["n"] += 1
        _write_timeout_error()

    request_data = FakeRequestData({"video": ("clip.mp4", Unrewindable(), "video/mp4")})

    with patch.object(HTTPXRequest, "do_request", always_stall):
        with pytest.raises(TimedOut):
            await ResilientHTTPXRequest().do_request(
                url="https://api.telegram.org", method="POST", request_data=request_data
            )

    assert calls["n"] == 1
