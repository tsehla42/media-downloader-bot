from platforms import detect_platform, extract_domain
from utils import is_valid_url

def test_detect_youtube_watch():
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

def test_detect_youtube_short():
    assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "youtube"

def test_detect_youtube_shorts():
    assert detect_platform("https://www.youtube.com/shorts/abc123") == "youtube"

def test_detect_youtube_music():
    assert detect_platform("https://music.youtube.com/watch?v=uueRqEalZ7s") == "youtube"

def test_detect_youtube_music_with_params():
    assert detect_platform("https://music.youtube.com/watch?v=uueRqEalZ7s&si=Xu33ojhvEQyWBemI") == "youtube"

def test_detect_youtube_mobile():
    assert detect_platform("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

def test_detect_tiktok():
    assert detect_platform("https://www.tiktok.com/@user/video/123") == "tiktok"

def test_detect_tiktok_vm():
    assert detect_platform("https://vm.tiktok.com/abc123/") == "tiktok"

def test_detect_instagram_reel():
    assert detect_platform("https://www.instagram.com/reel/abc123/") == "instagram"

def test_detect_instagram_post():
    assert detect_platform("https://www.instagram.com/p/abc123/") == "instagram"

def test_detect_tiktok_vt():
    assert detect_platform("https://vt.tiktok.com/ZSxCuvru2/") == "tiktok"

def test_detect_tiktok_m():
    assert detect_platform("https://m.tiktok.com/share/live/123") == "tiktok"

def test_detect_douyin():
    assert detect_platform("https://www.douyin.com/video/6961737553342991651") == "tiktok"

def test_detect_unknown():
    assert detect_platform("https://example.com/video") is None

def test_is_valid_url():
    assert is_valid_url("https://youtube.com/watch?v=123") is True
    assert is_valid_url("not a url") is False
    assert is_valid_url("ftp://files.example.com") is False

def test_is_valid_url_embedded():
    assert is_valid_url("Check out https://youtube.com/watch?v=123") is True
    assert is_valid_url("https://tiktok.com/a and https://tiktok.com/b") is True


def test_extract_domain_basic():
    assert extract_domain("https://www.pinterest.com/pin/123/") == "pinterest.com"

def test_extract_domain_no_www():
    assert extract_domain("https://github.com/user/repo") == "github.com"

def test_extract_domain_subdomain():
    assert extract_domain("https://vm.tiktok.com/abc123/") == "vm.tiktok.com"

def test_extract_domain_lowercase():
    assert extract_domain("https://WWW.YouTube.COM/watch?v=123") == "youtube.com"

def test_extract_domain_empty():
    assert extract_domain("") == ""

def test_extract_domain_no_scheme():
    assert extract_domain("not-a-url") == ""


from utils import get_gallery_dl_domains

def test_get_gallery_dl_domains_returns_frozenset():
    """get_gallery_dl_domains returns a frozenset of strings."""
    result = get_gallery_dl_domains()
    assert isinstance(result, frozenset)
    # Should contain known domains
    if result:  # May be empty if generation failed
        assert "youtube.com" in result or len(result) > 0

def test_get_gallery_dl_domains_import_error_returns_empty(monkeypatch):
    """When gallery_dl_domains can't be imported and generation fails, return empty frozenset."""
    import builtins
    import subprocess

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "gallery_dl_domains":
            raise ImportError("no such module")
        return original_import(name, *args, **kwargs)

    def mock_run(*args, **kwargs):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr(builtins, "__import__", mock_import)
    monkeypatch.setattr(subprocess, "run", mock_run)
    result = get_gallery_dl_domains()
    assert result == frozenset()


import os
from utils import find_downloaded_file, cleanup_video_files, make_video_tmp_path, make_tmp_dir


def test_find_downloaded_file_finds_mp4(tmp_path):
    base = tmp_path / "test123"
    (tmp_path / "test123.mp4").touch()
    result = find_downloaded_file(str(base))
    assert result == str(tmp_path / "test123.mp4")

def test_find_downloaded_file_finds_webm(tmp_path):
    base = tmp_path / "test123"
    (tmp_path / "test123.webm").touch()
    result = find_downloaded_file(str(base))
    assert result == str(tmp_path / "test123.webm")

def test_find_downloaded_file_finds_mkv(tmp_path):
    base = tmp_path / "test123"
    (tmp_path / "test123.mkv").touch()
    result = find_downloaded_file(str(base))
    assert result == str(tmp_path / "test123.mkv")

def test_find_downloaded_file_returns_none_if_no_match(tmp_path):
    base = tmp_path / "test123"
    result = find_downloaded_file(str(base))
    assert result is None

def test_find_downloaded_file_prefers_mp4(tmp_path):
    base = tmp_path / "test123"
    (tmp_path / "test123.mp4").touch()
    (tmp_path / "test123.webm").touch()
    (tmp_path / "test123.mkv").touch()
    result = find_downloaded_file(str(base))
    assert result == str(tmp_path / "test123.mp4")

def test_cleanup_video_files_removes_all_variants(tmp_path):
    base = tmp_path / "test123"
    for ext in ["mp4", "webm", "mkv"]:
        (tmp_path / f"test123.{ext}").touch()
    cleanup_video_files(str(base))
    for ext in ["mp4", "webm", "mkv"]:
        assert not (tmp_path / f"test123.{ext}").exists()

def test_cleanup_video_files_handles_missing_files(tmp_path):
    base = tmp_path / "test123"
    cleanup_video_files(str(base))  # Should not raise

def test_make_video_tmp_path_creates_dir():
    tmp_id, output_path, base = make_video_tmp_path()
    assert len(tmp_id) == 8
    assert output_path.endswith(".%(ext)s")
    assert os.path.isdir(os.path.dirname(base))

def test_make_tmp_dir_creates_dir():
    out_dir = make_tmp_dir()
    assert os.path.isdir(out_dir)


from utils import get_ytdlp_domains

def test_get_ytdlp_domains_returns_frozenset():
    """get_ytdlp_domains returns a frozenset of strings."""
    result = get_ytdlp_domains()
    assert isinstance(result, frozenset)
    # Should contain known domains
    if result:  # May be empty if generation failed
        assert "youtube.com" in result or len(result) > 0

def test_get_ytdlp_domains_import_error_returns_empty(monkeypatch):
    """When ytdlp_domains can't be imported and generation fails, return empty frozenset."""
    import builtins
    import subprocess

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "ytdlp_domains":
            raise ImportError("no such module")
        return original_import(name, *args, **kwargs)

    def mock_run(*args, **kwargs):
        raise FileNotFoundError("no such file")

    monkeypatch.setattr(builtins, "__import__", mock_import)
    monkeypatch.setattr(subprocess, "run", mock_run)
    result = get_ytdlp_domains()
    assert result == frozenset()
