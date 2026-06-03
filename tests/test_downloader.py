import json
import sys
from unittest.mock import patch, MagicMock
from downloader import get_metadata, download_video, download_audio, download_gallery_dl_images, _find_gallery_dl

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
