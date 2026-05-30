import json
import sys
from unittest.mock import patch, MagicMock
from downloader import get_metadata, download_video, download_audio, download_instagram_image

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

def test_download_instagram_image_uses_instaloader():
    mock_il = MagicMock()
    with patch.dict("sys.modules", {"instaloader": mock_il}):
        mock_L = MagicMock()
        mock_il.Instaloader.return_value = mock_L

        mock_post = MagicMock()
        mock_post.typename = "GraphImage"
        mock_post.is_video = False
        mock_il.Post.from_shortcode.return_value = mock_post

        with patch("downloader.os.listdir", return_value=["test_image.jpg"]):
            with patch("downloader.shutil.copy2"):
                with patch("downloader.os.path.isfile", return_value=True):
                    with patch("downloader.tempfile.TemporaryDirectory"):
                        result = download_instagram_image("https://instagram.com/p/ABC123/", "/tmp/test.jpg")
                        assert result is True

def test_download_instagram_image_returns_false_on_error():
    mock_il = MagicMock()
    mock_il.Instaloader.side_effect = Exception("Import error")
    with patch.dict("sys.modules", {"instaloader": mock_il}):
        result = download_instagram_image("https://instagram.com/p/abc/", "/tmp/test.jpg")
        assert result is False

def test_download_instagram_image_returns_false_for_video():
    mock_il = MagicMock()
    with patch.dict("sys.modules", {"instaloader": mock_il}):
        mock_L = MagicMock()
        mock_il.Instaloader.return_value = mock_L

        mock_post = MagicMock()
        mock_post.typename = "GraphVideo"
        mock_post.is_video = True
        mock_il.Post.from_shortcode.return_value = mock_post

        result = download_instagram_image("https://instagram.com/p/ABC123/", "/tmp/test.jpg")
        assert result is False

def test_download_instagram_image_returns_false_for_carousel():
    mock_il = MagicMock()
    with patch.dict("sys.modules", {"instaloader": mock_il}):
        mock_L = MagicMock()
        mock_il.Instaloader.return_value = mock_L

        mock_post = MagicMock()
        mock_post.typename = "GraphSidecar"
        mock_post.is_video = False
        mock_il.Post.from_shortcode.return_value = mock_post

        result = download_instagram_image("https://instagram.com/p/ABC123/", "/tmp/test.jpg")
        assert result is False
