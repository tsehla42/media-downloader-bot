from utils import detect_platform, is_valid_url

def test_detect_youtube_watch():
    assert detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"

def test_detect_youtube_short():
    assert detect_platform("https://youtu.be/dQw4w9WgXcQ") == "youtube"

def test_detect_youtube_shorts():
    assert detect_platform("https://www.youtube.com/shorts/abc123") == "youtube"

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
