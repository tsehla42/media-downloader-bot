import json
from unittest.mock import patch, MagicMock
from downloader import get_metadata, download_video, download_audio

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
