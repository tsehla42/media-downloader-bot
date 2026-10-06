import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from downloader import get_metadata, download_video, download_audio, download_gallery_dl_images, download_gallery_dl_video, _find_gallery_dl

SAMPLE_METADATA = {
    "id": "abc123",
    "title": "Test Video",
    "duration": 120,
    "thumbnail": "https://example.com/thumb.jpg",
    "extractor": "youtube",
    "filesize_approx": 5000000,
}

def test_get_metadata_calls_ytdlp():
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(SAMPLE_METADATA),
            stderr=""
        )
        result = get_metadata("https://youtube.com/watch?v=abc123")
        assert result["title"] == "Test Video"
        assert result["duration"] == 120
        call_args = mock_run.call_args[0][0]
        assert "--dump-json" in call_args


def test_get_metadata_passes_format_selector():
    """get_metadata passes -f flag when format_selector is provided."""
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(SAMPLE_METADATA),
            stderr=""
        )
        fmt = "best[ext=mp4][filesize<52428800]/best[ext=mp4]/best[filesize<52428800]/best"
        result = get_metadata("https://youtube.com/watch?v=abc123", format_selector=fmt)
        assert result["title"] == "Test Video"
        call_args = mock_run.call_args[0][0]
        assert "-f" in call_args
        assert fmt in call_args


def test_get_metadata_omits_format_selector_by_default():
    """get_metadata does not pass -f flag when format_selector is None."""
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(SAMPLE_METADATA),
            stderr=""
        )
        result = get_metadata("https://youtube.com/watch?v=abc123")
        assert result["title"] == "Test Video"
        call_args = mock_run.call_args[0][0]
        assert "-f" not in call_args


def test_video_format_selector_includes_merge_branches():
    """VIDEO_FORMAT_SELECTOR must try bestvideo+bestaudio merge first.

    YouTube increasingly serves DASH-only formats (no progressive
    video+audio stream), for which a bare "best" selector fails with
    "Requested format is not available".
    """
    from downloader import VIDEO_FORMAT_SELECTOR
    assert "bestvideo" in VIDEO_FORMAT_SELECTOR
    assert "+bestaudio" in VIDEO_FORMAT_SELECTOR
    # Merge branches must come before the bare "best" fallback
    assert VIDEO_FORMAT_SELECTOR.index("+bestaudio") < VIDEO_FORMAT_SELECTOR.rindex("/best")


def test_download_video_selectors_include_merge_branches():
    """download_video first attempt and retry must both support DASH-only formats."""
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="File is too large"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        result = download_video("https://youtube.com/watch?v=abc123", "/tmp/test.mp4")
        assert result is True

        first_args = mock_run.call_args_list[0][0][0]
        first_fmt = first_args[first_args.index("-f") + 1]
        assert "bestvideo" in first_fmt
        assert "+bestaudio" in first_fmt

        retry_args = mock_run.call_args_list[1][0][0]
        retry_fmt = retry_args[retry_args.index("-f") + 1]
        assert "worstvideo" in retry_fmt
        assert "+worstaudio" in retry_fmt
        assert "worst[filesize<" in retry_fmt


def test_video_format_selector_prefers_avc1_then_av1_with_size_ladders():
    """H.264 first (plays on every Telegram client, incl. iPhone), then AV1.

    Each codec phase is size-limited first: yt-dlp drops over-limit rungs and
    picks the best remaining one (1080p > 50MB -> 720p -> 480p -> ...).
    The selector must end with catch-all branches so a video is always sent
    when one exists, rather than failing with an error.
    """
    from downloader import VIDEO_FORMAT_SELECTOR
    b = VIDEO_FORMAT_SELECTOR.split("/")
    assert len(b) == 10
    # 1-2: H.264 DASH merge — size ladder, then uncapped avc1
    assert b[0].startswith("bestvideo[ext=mp4][vcodec^=avc1][filesize<")
    assert b[1] == "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"
    # 3-4: H.264 progressive single-file — size ladder, then uncapped
    assert b[2].startswith("best[ext=mp4][vcodec^=avc1][filesize<")
    assert b[3] == "best[ext=mp4][vcodec^=avc1]"
    # 5-6: AV1/any-mp4 DASH merge — only after all avc1 options are exhausted
    assert b[4].startswith("bestvideo[ext=mp4][filesize<")
    assert b[5] == "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
    # 7-8: progressive fallback, 9-10: catch-all that always yields something
    assert b[6].startswith("best[ext=mp4][filesize<")
    assert b[7] == "best[ext=mp4]"
    assert b[8].startswith("best[filesize<")
    assert b[9] == "best"


def test_instagram_format_selector_prefers_h264_progressive():
    """Instagram DASH is VP9 (unplayable on iPhone); H.264 progressive wins.

    Instagram's H.264 rendition has no vcodec metadata (codec filters skip
    it), so the unfiltered progressive branch must come before any DASH
    merge. VP9 merge stays as last-resort so a video is still delivered.
    """
    from downloader import INSTAGRAM_FORMAT_SELECTOR
    b = INSTAGRAM_FORMAT_SELECTOR.split("/")
    assert b[0].startswith("bestvideo[ext=mp4][vcodec^=avc1][filesize<")
    prog = next(i for i, x in enumerate(b) if x.startswith("best[ext=mp4]"))
    dash = b.index("bestvideo[ext=mp4]+bestaudio[ext=m4a]")
    assert prog < dash
    assert b[-1] == "best"


def test_download_video_picks_selector_by_platform():
    """Instagram platform arg switches to the progressive-first selector."""
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        download_video("https://www.instagram.com/reel/abc/", "/tmp/t.%(ext)s", platform="instagram")
        args = mock_run.call_args[0][0]
        ig_fmt = args[args.index("-f") + 1]
    b = ig_fmt.split("/")
    prog = next(i for i, x in enumerate(b) if x.startswith("best[ext=mp4]"))
    dash = b.index("bestvideo[ext=mp4]+bestaudio[ext=m4a]")
    assert prog < dash, "Instagram must prefer progressive H.264 over VP9 DASH merge"

    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        download_video("https://youtube.com/watch?v=abc", "/tmp/t.%(ext)s")
        args = mock_run.call_args[0][0]
        yt_fmt = args[args.index("-f") + 1]
    b = yt_fmt.split("/")
    assert b[0].startswith("bestvideo[ext=mp4][vcodec^=avc1][filesize<")
    dash = b.index("bestvideo[ext=mp4]+bestaudio[ext=m4a]")
    bare_prog = next(i for i, x in enumerate(b) if x == "best[ext=mp4]")
    assert dash < bare_prog, "generic selector keeps DASH merge before bare progressive"


def test_download_video_retry_prefers_avc1_then_catch_all():
    """Retry selector mirrors the attempt selector: avc1 first, always ends
    with a catch-all so a low-quality video beats an error."""
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="fail"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        download_video("https://youtube.com/watch?v=abc", "/tmp/t.%(ext)s")
        args = mock_run.call_args_list[1][0][0]
        retry_fmt = args[args.index("-f") + 1]
    b = retry_fmt.split("/")
    assert b[0].startswith("worstvideo[ext=mp4][vcodec^=avc1][filesize<")
    assert any(x.startswith("worst[filesize<") for x in b)
    assert b[-1] == "worst"


def test_apply_faststart_finds_ytdlp_output_file(tmp_path):
    """_apply_faststart must resolve '<id>.%(ext)s' to '<id>.mp4'.

    It previously built '<id>..mp4' (double dot), so the downloaded file was
    never found and faststart never ran — and the logging call raised
    NameError (details_logger is not imported in downloader).
    """
    from downloader import _apply_faststart
    video = tmp_path / "abc123.mp4"
    video.write_bytes(b"data")
    with patch("downloader._ensure_faststart", return_value=str(video)) as mock_fs, \
         patch("downloader.logger") as mock_log:
        _apply_faststart(str(tmp_path / "abc123.%(ext)s"), {"url": "https://x"})
    mock_fs.assert_called_once_with(str(video))
    mock_log.info.assert_any_call("faststart applied", extra={"url": "https://x"})


def test_apply_faststart_handles_literal_path(tmp_path):
    """A literal .mp4 path (no %(ext)s template) must be found as-is."""
    from downloader import _apply_faststart
    video = tmp_path / "video.mp4"
    video.write_bytes(b"data")
    with patch("downloader._ensure_faststart", return_value=str(video)) as mock_fs:
        _apply_faststart(str(video), {})
    mock_fs.assert_called_once_with(str(video))


def test_get_metadata_returns_none_on_failure():
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ERROR: Video not found"
        )
        result = get_metadata("https://youtube.com/watch?v=invalid")
        assert result is None

def test_download_video_calls_ytdlp():
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        result = download_video("https://youtube.com/watch?v=abc123", "/tmp/test.mp4")
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "-f" in call_args
        assert "/tmp/test.mp4" in call_args

def test_download_video_retries_on_too_large():
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="File is too large"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        result = download_video("https://youtube.com/watch?v=abc123", "/tmp/test.mp4")
        assert result is True
        assert mock_run.call_count == 2


def test_download_video_fallback_prefers_quality_constrained_worst():
    """Fallback should use 'worst[filesize<50MB]/worst' to avoid watermarked formats.

    TikTok's download_addr (watermarked) can be smaller than play_addr (clean).
    Using bare 'worst' may pick the watermarked version. Constraining by filesize
    first tries a small clean format before falling back to bare worst.
    """
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="File is too large"),
            MagicMock(returncode=0, stdout="", stderr=""),
        ]
        result = download_video("https://tiktok.com/@user/video/123", "/tmp/test.mp4")
        assert result is True
        assert mock_run.call_count == 2
        # Check the fallback command uses filesize-constrained worst
        fallback_args = mock_run.call_args_list[1][0][0]
        format_idx = fallback_args.index("-f")
        format_value = fallback_args[format_idx + 1]
        assert "worst[filesize<" in format_value

def test_download_audio_uses_extract_audio():
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        result = download_audio("https://youtube.com/watch?v=abc123", "/tmp/test.mp3")
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "--extract-audio" in call_args
        assert "--audio-format" in call_args


def test_download_gallery_dl_images_calls_gallery_dl():
    with patch("downloader.subprocess.run") as mock_run, \
         patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"), \
         patch("downloader.os.path.isfile", return_value=True), \
         patch("downloader.glob.glob", side_effect=[
             ["/tmp/test_output/image.jpg"],  # *.jpg
             [],  # *.jpeg
             [],  # *.png
             [],  # *.webp
         ]):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        with patch("downloader.os.makedirs"):
            result = download_gallery_dl_images(
                "https://instagram.com/p/ABC123/",
                "/tmp/test_output",
                cookies="/tmp/cookies.txt"
            )
            assert result == ["/tmp/test_output/image.jpg"]
            call_args = mock_run.call_args[0][0]
            assert "gallery-dl" in call_args[0]
            assert "--cookies" in call_args
            assert "/tmp/cookies.txt" in call_args


def test_download_gallery_dl_images_returns_empty_on_failure():
    with patch("downloader.subprocess.run") as mock_run, \
         patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ERROR: some error"
        )
        with patch("downloader.os.makedirs"):
            result = download_gallery_dl_images(
                "https://instagram.com/p/ABC123/",
                "/tmp/test_output",
                cookies="/tmp/cookies.txt"
            )
            assert result == []


def test_download_gallery_dl_images_works_without_cookies():
    """gallery-dl can download without cookies (e.g. TikTok)."""
    with patch("downloader.subprocess.run") as mock_run, \
         patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"), \
         patch("downloader.glob.glob", side_effect=[
             ["/tmp/test_output/image.jpg"],  # *.jpg
             [],  # *.jpeg
             [],  # *.png
             [],  # *.webp
         ]):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        with patch("downloader.os.makedirs"):
            result = download_gallery_dl_images(
                "https://tiktok.com/@user/photo/123",
                "/tmp/test_output",
                cookies=""
            )
            assert result == ["/tmp/test_output/image.jpg"]
            # Verify --cookies was NOT passed
            call_args = mock_run.call_args[0][0]
            assert "--cookies" not in call_args


def test_download_gallery_dl_images_returns_empty_when_not_installed():
    with patch("downloader._find_gallery_dl", return_value=None):
        result = download_gallery_dl_images(
            "https://instagram.com/p/ABC123/",
            "/tmp/test_output",
            cookies="/tmp/cookies.txt"
        )
        assert result == []


def test_find_gallery_dl_uses_venv_fallback():
    """_find_gallery_dl falls back to venv bin/ when not in PATH."""
    import sys
    with patch("downloader.shutil.which", return_value=None), \
         patch("downloader.sys.executable", "/home/user/.venv/bin/python"), \
         patch("downloader.os.path.dirname", return_value="/home/user/.venv/bin"), \
         patch("downloader.os.path.isfile", return_value=True), \
         patch("downloader.os.access", return_value=True):
        result = _find_gallery_dl()
        assert result == "/home/user/.venv/bin/gallery-dl"


def test_download_gallery_dl_video_calls_gallery_dl():
    with patch("downloader.subprocess.run") as mock_run, \
         patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"), \
         patch("downloader.glob.glob", side_effect=[
             [],  # *.mp4
             ["/tmp/test_output/video.webm"],  # *.webm
             [],  # *.mkv
             [],  # *.mov
         ]), \
         patch("downloader.os.path.getsize", return_value=1024*1024), \
         patch("downloader._ensure_faststart", return_value="/tmp/test_output/video.webm"):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        with patch("downloader.os.makedirs"):
            result = download_gallery_dl_video(
                "https://example.com/post",
                "/tmp/test_output",
            )
            assert result == "/tmp/test_output/video.webm"
            call_args = mock_run.call_args[0][0]
            assert "gallery-dl" in call_args[0]
            assert "-d" in call_args


def test_download_gallery_dl_video_returns_none_on_failure():
    with patch("downloader.subprocess.run") as mock_run, \
         patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"):
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ERROR: Unsupported URL"
        )
        with patch("downloader.os.makedirs"):
            result = download_gallery_dl_video(
                "https://example.com/unknown",
                "/tmp/test_output",
            )
            assert result is None


def test_download_gallery_dl_video_returns_none_when_not_installed():
    with patch("downloader._find_gallery_dl", return_value=None):
        result = download_gallery_dl_video(
            "https://example.com/post",
            "/tmp/test_output",
        )
        assert result is None


def test_download_gallery_dl_video_returns_none_when_no_videos_found():
    with patch("downloader.subprocess.run") as mock_run, \
         patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"), \
         patch("downloader.glob.glob", return_value=[]):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )
        with patch("downloader.os.makedirs"):
            result = download_gallery_dl_video(
                "https://example.com/image-only",
                "/tmp/test_output",
            )
            assert result is None


def test_download_video_raises_auth_required_on_login_error():
    """download_video raises DownloadAuthRequired when yt-dlp says login needed."""
    from downloader import DownloadAuthRequired

    login_error = (
        "ERROR: [TikTok] 7653539007543921940: This post may not be comfortable "
        "for some audiences. Log in for access. Use --cookies-from-browser or "
        "--cookies for the authentication."
    )
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=login_error),
            MagicMock(returncode=1, stdout="", stderr=login_error),
        ]
        with pytest.raises(DownloadAuthRequired):
            download_video("https://tiktok.com/@user/video/123", "/tmp/test.mp4")


def test_download_video_raises_auth_required_on_instagram_content_restriction():
    """download_video raises DownloadAuthRequired for restricted Instagram content."""
    from downloader import DownloadAuthRequired

    restriction_error = (
        "ERROR: [Instagram] DUruRXWChNQ: This content isn't available to everyone: "
        "It can't be seen by certain audiences."
    )
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=restriction_error),
            MagicMock(returncode=1, stdout="", stderr=restriction_error),
        ]
        with pytest.raises(DownloadAuthRequired):
            download_video("https://www.instagram.com/reel/DUruRXWChNQ", "/tmp/test.mp4")


def test_download_video_raises_auth_required_on_age_restricted():
    """download_video raises DownloadAuthRequired for age-restricted YouTube content."""
    from downloader import DownloadAuthRequired

    age_restricted_error = (
        "ERROR: [youtube] uueRqEalZ7s: Sign in to confirm your age. "
        "This video may be inappropriate for some users. "
        "Use --cookies-from-browser or --cookies for the authentication."
    )
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr=age_restricted_error),
            MagicMock(returncode=1, stdout="", stderr=age_restricted_error),
        ]
        with pytest.raises(DownloadAuthRequired):
            download_video("https://youtube.com/watch?v=uueRqEalZ7s", "/tmp/test.mp4")


def test_download_video_does_not_raise_on_generic_failure():
    """download_video returns False for non-auth failures."""
    with patch("downloader.subprocess.run") as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1, stdout="", stderr="ERROR: File not found"),
            MagicMock(returncode=1, stdout="", stderr="ERROR: File not found"),
        ]
        result = download_video("https://youtube.com/watch?v=abc", "/tmp/test.mp4")
        assert result is False


# ---------------------------------------------------------------------------
# DownloadError tests
# ---------------------------------------------------------------------------


def test_download_error_stores_user_message_and_raw_error():
    """DownloadError stores both user-facing message and raw technical details."""
    from downloader import DownloadError

    err = DownloadError("Could not download. Please try again.", raw_error="timeout details")
    assert err.user_message == "Could not download. Please try again."
    assert err.raw_error == "timeout details"
    assert str(err) == "Could not download. Please try again."


def test_download_error_raw_error_optional():
    """DownloadError works without raw_error."""
    from downloader import DownloadError

    err = DownloadError("Something went wrong")
    assert err.user_message == "Something went wrong"
    assert err.raw_error is None


def test_download_gallery_dl_images_raises_on_timeout():
    """download_gallery_dl_images raises DownloadError on subprocess timeout."""
    import subprocess as sp
    from downloader import DownloadError

    with patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"), \
         patch("downloader.subprocess.run", side_effect=sp.TimeoutExpired(cmd="gallery-dl", timeout=60)):
        with pytest.raises(DownloadError) as exc_info:
            download_gallery_dl_images("https://example.com/page", "/tmp/out")
        assert "Could not fetch" in exc_info.value.user_message
        assert "timed out" in exc_info.value.raw_error


def test_download_gallery_dl_video_raises_on_timeout():
    """download_gallery_dl_video raises DownloadError on subprocess timeout."""
    import subprocess as sp
    from downloader import DownloadError

    with patch("downloader._find_gallery_dl", return_value="/usr/bin/gallery-dl"), \
         patch("downloader.subprocess.run", side_effect=sp.TimeoutExpired(cmd="gallery-dl", timeout=60)):
        with pytest.raises(DownloadError) as exc_info:
            download_gallery_dl_video("https://example.com/page", "/tmp/out")
        assert "Could not fetch" in exc_info.value.user_message
        assert "timed out" in exc_info.value.raw_error


class TestYouTubeCookies:
    """YT_COOKIES_PATH is passed to yt-dlp for YouTube URLs when the file exists."""

    @pytest.fixture
    def yt_cookies(self, tmp_path):
        cookie_file = tmp_path / "yt-cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        return str(cookie_file)

    def test_get_metadata_passes_cookies_for_youtube_url(self, yt_cookies):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", yt_cookies):
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_METADATA), stderr="")
            get_metadata("https://www.youtube.com/watch?v=abc123")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" in call_args
            assert yt_cookies in call_args

    def test_get_metadata_passes_cookies_for_youtu_be_url(self, yt_cookies):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", yt_cookies):
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_METADATA), stderr="")
            get_metadata("https://youtu.be/abc123")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" in call_args
            assert yt_cookies in call_args

    def test_get_metadata_no_cookies_for_non_youtube_url(self, yt_cookies):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", yt_cookies):
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_METADATA), stderr="")
            get_metadata("https://example.com/video")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" not in call_args

    def test_get_metadata_no_cookies_when_file_missing(self):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", "/nonexistent/yt-cookies.txt"):
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_METADATA), stderr="")
            get_metadata("https://www.youtube.com/watch?v=abc123")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" not in call_args

    def test_download_video_passes_cookies_for_youtube_url(self, yt_cookies):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", yt_cookies):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            download_video("https://www.youtube.com/watch?v=abc123", "/tmp/test.mp4")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" in call_args
            assert yt_cookies in call_args

    def test_download_video_no_cookies_for_non_youtube_url(self, yt_cookies):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", yt_cookies):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            download_video("https://example.com/video", "/tmp/test.mp4")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" not in call_args

    def test_download_audio_passes_cookies_for_youtube_url(self, yt_cookies):
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", yt_cookies):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            download_audio("https://www.youtube.com/watch?v=abc123", "/tmp/test.mp3")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" in call_args
            assert yt_cookies in call_args

    def test_get_metadata_no_cookies_when_file_empty(self, tmp_path):
        """An empty yt-cookies.txt (placeholder) is treated as missing."""
        cookie_file = tmp_path / "yt-cookies.txt"
        cookie_file.write_text("")
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.YT_COOKIES_PATH", str(cookie_file)):
            mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(SAMPLE_METADATA), stderr="")
            get_metadata("https://www.youtube.com/watch?v=abc123")
            call_args = mock_run.call_args[0][0]
            assert "--cookies" not in call_args


# ---------------------------------------------------------------------------
# download_tiktok_photo_images — TikTok photo posts via yt-dlp --write-pages
# ---------------------------------------------------------------------------

PHOTO_PAGE_DUMP = (
    '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
    + json.dumps({
        "__DEFAULT_SCOPE__": {
            "webapp.video-detail": {
                "statusCode": 0,
                "itemInfo": {"itemStruct": {"id": "123", "imagePost": {"images": [
                    {"imageURL": {"urlList": ["https://cdn.example.com/a1.jpeg", "https://cdn.example.com/a1x.jpeg"]}},
                    {"imageURL": {"urlList": ["https://cdn.example.com/a2.jpeg"]}},
                ]}}},
            }
        }
    })
    + "</script></html>"
)

VIDEO_PAGE_DUMP = (
    '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'
    + json.dumps({
        "__DEFAULT_SCOPE__": {
            "webapp.video-detail": {
                "statusCode": 0,
                "itemInfo": {"itemStruct": {"id": "123", "video": {"playAddr": "https://cdn.example.com/v.mp4"}}},
            }
        }
    })
    + "</script></html>"
)


def _dump_writer(dump_text, returncode=0):
    """subprocess.run side effect: write a page dump into the yt-dlp cwd."""
    def _run(cmd, **kwargs):
        cwd = kwargs.get("cwd")
        assert cwd, "yt-dlp must run with cwd set so page dumps land in a temp dir"
        with open(os.path.join(cwd, "page.dump"), "w") as f:
            f.write(dump_text)
        return MagicMock(returncode=returncode, stdout="", stderr="boom" if returncode else "")
    return _run


def _httpx_client_mock(head_url=None):
    """Build a patch target for downloader.httpx.Client (resolve + image download)."""
    client = MagicMock()
    if head_url is not None:
        client.head.return_value = MagicMock(url=head_url)
    resp = MagicMock()
    resp.content = b"\xff\xd8fakejpeg"
    resp.raise_for_status = MagicMock()
    resp.headers = {"content-type": "image/jpeg"}
    client.get.return_value = resp
    cm = MagicMock()
    cm.__enter__.return_value = client
    cm.__exit__.return_value = False
    return MagicMock(return_value=cm), client


class TestDownloadTiktokPhotoImages:
    """Tests for download_tiktok_photo_images."""

    def test_photo_url_returns_downloaded_files(self, tmp_path):
        from downloader import download_tiktok_photo_images
        client_patch, _ = _httpx_client_mock()
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP)) as mock_run, \
             patch("downloader.httpx.Client", client_patch):
            files = download_tiktok_photo_images(
                "https://www.tiktok.com/@user/photo/123", str(tmp_path)
            )

        assert len(files) == 2
        for f in files:
            assert os.path.isfile(f)
            with open(f, "rb") as fh:
                assert fh.read() == b"\xff\xd8fakejpeg"
        # /photo/ rewritten to /video/ because yt-dlp only matches /video/
        cmd = mock_run.call_args[0][0]
        assert "https://www.tiktok.com/@user/video/123" in cmd
        assert not any("/photo/" in arg for arg in cmd)

    def test_video_url_returns_empty_without_side_effects(self, tmp_path):
        from downloader import download_tiktok_photo_images
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.httpx.Client") as mock_client:
            files = download_tiktok_photo_images(
                "https://www.tiktok.com/@user/video/123", str(tmp_path)
            )

        assert files == []
        mock_run.assert_not_called()
        mock_client.assert_not_called()

    def test_short_url_resolving_to_photo_extracts(self, tmp_path):
        from downloader import download_tiktok_photo_images
        client_patch, _ = _httpx_client_mock(
            head_url="https://www.tiktok.com/@user/photo/999"
        )
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP)) as mock_run, \
             patch("downloader.httpx.Client", client_patch):
            files = download_tiktok_photo_images("https://vt.tiktok.com/ZSbPKwDAm/", str(tmp_path))

        assert len(files) == 2
        cmd = mock_run.call_args[0][0]
        assert "https://www.tiktok.com/@user/video/999" in cmd

    def test_short_url_resolving_to_video_returns_empty(self, tmp_path):
        from downloader import download_tiktok_photo_images
        client_patch, _ = _httpx_client_mock(
            head_url="https://www.tiktok.com/@user/video/999"
        )
        with patch("downloader.subprocess.run") as mock_run, \
             patch("downloader.httpx.Client", client_patch):
            files = download_tiktok_photo_images("https://vt.tiktok.com/ZSxyz/", str(tmp_path))

        assert files == []
        mock_run.assert_not_called()

    def test_ytdlp_failure_raises_image_post_error(self, tmp_path):
        from downloader import download_tiktok_photo_images, DownloadError
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP, returncode=1)), \
             patch("downloader.download_gallery_dl_images", return_value=[]), \
             patch("downloader.httpx.Client") as mock_client:
            with pytest.raises(DownloadError) as exc:
                download_tiktok_photo_images(
                    "https://www.tiktok.com/@user/photo/123", str(tmp_path)
                )

        assert exc.value.user_message == "Could not fetch this image post"
        mock_client.assert_not_called()

    def test_dump_without_imagepost_raises_image_post_error(self, tmp_path):
        from downloader import download_tiktok_photo_images, DownloadError
        with patch("downloader.subprocess.run", side_effect=_dump_writer(VIDEO_PAGE_DUMP)), \
             patch("downloader.download_gallery_dl_images", return_value=[]), \
             patch("downloader.httpx.Client") as mock_client:
            with pytest.raises(DownloadError) as exc:
                download_tiktok_photo_images(
                    "https://www.tiktok.com/@user/photo/123", str(tmp_path)
                )

        assert exc.value.user_message == "Could not fetch this image post"
        mock_client.assert_not_called()

    def test_photo_extraction_failure_rescued_by_gallery_dl(self, tmp_path):
        """gallery-dl safety net still rescues when the page-dump path fails."""
        from downloader import download_tiktok_photo_images
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP, returncode=1)), \
             patch("downloader.download_gallery_dl_images", return_value=["/tmp/gdl.jpg"]) as mock_gdl:
            files = download_tiktok_photo_images(
                "https://www.tiktok.com/@user/photo/123", str(tmp_path)
            )

        assert files == ["/tmp/gdl.jpg"]
        mock_gdl.assert_called_once()

    def test_image_download_failure_raises_image_post_error(self, tmp_path):
        """A failed image fetch falls through gallery-dl and raises the specific error."""
        from downloader import download_tiktok_photo_images, DownloadError
        client_patch, client = _httpx_client_mock()
        client.get.return_value.raise_for_status.side_effect = RuntimeError("network down")
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP)), \
             patch("downloader.download_gallery_dl_images", return_value=[]), \
             patch("downloader.httpx.Client", client_patch):
            with pytest.raises(DownloadError) as exc:
                download_tiktok_photo_images(
                    "https://www.tiktok.com/@user/photo/123", str(tmp_path)
                )

        assert exc.value.user_message == "Could not fetch this image post"

    def test_passes_cookies_when_file_exists(self, tmp_path):
        from downloader import download_tiktok_photo_images
        cookie_file = tmp_path / "tt-cookies.txt"
        cookie_file.write_text("# Netscape HTTP Cookie File\n")
        client_patch, _ = _httpx_client_mock()
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP)) as mock_run, \
             patch("downloader.httpx.Client", client_patch):
            download_tiktok_photo_images(
                "https://www.tiktok.com/@user/photo/123", str(tmp_path), str(cookie_file)
            )

        cmd = mock_run.call_args[0][0]
        assert "--cookies" in cmd
        assert str(cookie_file) in cmd

    def test_no_cookies_flag_when_file_missing(self, tmp_path):
        from downloader import download_tiktok_photo_images
        client_patch, _ = _httpx_client_mock()
        with patch("downloader.subprocess.run", side_effect=_dump_writer(PHOTO_PAGE_DUMP)) as mock_run, \
             patch("downloader.httpx.Client", client_patch):
            download_tiktok_photo_images(
                "https://www.tiktok.com/@user/photo/123", str(tmp_path), "/nonexistent/cookies.txt"
            )

        cmd = mock_run.call_args[0][0]
        assert "--cookies" not in cmd


# ---------------------------------------------------------------------------
# _resolve_tiktok_url — transient-failure resilience
# ---------------------------------------------------------------------------


class TestResolveTiktokUrl:
    """Redirect resolution must survive transient network hiccups."""

    def _client_factory(self, head=None, stream_url=None):
        """Build a downloader.httpx.Client patch; head is a list of side effects."""
        client = MagicMock()
        if head is not None:
            client.head.side_effect = head
        else:
            client.head.return_value = MagicMock(url="https://www.tiktok.com/@u/photo/1")
        if stream_url is not None:
            stream_cm = MagicMock()
            stream_cm.__enter__.return_value = MagicMock(url=stream_url)
            stream_cm.__exit__.return_value = False
            client.stream.return_value = stream_cm
        cm = MagicMock()
        cm.__enter__.return_value = client
        cm.__exit__.return_value = False
        return MagicMock(return_value=cm), client

    def test_retries_after_transient_timeout(self):
        from downloader import _resolve_tiktok_url
        import httpx
        client_patch, _ = self._client_factory(
            head=[httpx.ReadTimeout("The read operation timed out"),
                  MagicMock(url="https://www.tiktok.com/@u/photo/42")]
        )
        with patch("downloader.httpx.Client", client_patch), \
             patch("downloader.time.sleep"):
            final = _resolve_tiktok_url("https://vt.tiktok.com/ZSbba4FUF/")

        assert final == "https://www.tiktok.com/@u/photo/42"

    def test_get_fallback_when_head_always_times_out(self):
        from downloader import _resolve_tiktok_url
        import httpx
        client_patch, client = self._client_factory(
            head=httpx.ReadTimeout("The read operation timed out"),
            stream_url="https://www.tiktok.com/@u/photo/77",
        )
        with patch("downloader.httpx.Client", client_patch), \
             patch("downloader.time.sleep"):
            final = _resolve_tiktok_url("https://vt.tiktok.com/ZSxyz/")

        assert final == "https://www.tiktok.com/@u/photo/77"
        assert client.stream.called

    def test_raises_after_all_attempts_fail(self):
        from downloader import _resolve_tiktok_url
        import httpx
        client_patch, client = self._client_factory(head=httpx.ReadTimeout("timed out"))
        client.stream.side_effect = httpx.ReadTimeout("timed out")
        with patch("downloader.httpx.Client", client_patch), \
             patch("downloader.time.sleep"):
            with pytest.raises(httpx.HTTPError):
                _resolve_tiktok_url("https://vt.tiktok.com/ZSxyz/")

    def test_resolve_exhausted_returns_empty(self, tmp_path):
        """When resolution fails entirely, the pipeline falls through (not a photo)."""
        from downloader import download_tiktok_photo_images
        import httpx
        client_patch, client = self._client_factory(head=httpx.ReadTimeout("timed out"))
        client.stream.side_effect = httpx.ReadTimeout("timed out")
        with patch("downloader.httpx.Client", client_patch), \
             patch("downloader.time.sleep"), \
             patch("downloader.subprocess.run") as mock_run:
            files = download_tiktok_photo_images(
                "https://vt.tiktok.com/ZSxyz/", str(tmp_path)
            )

        assert files == []
        mock_run.assert_not_called()
