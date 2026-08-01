from core.url_parser import URLParser


def test_parse_video_url():
    url = "https://www.douyin.com/video/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed["type"] == "video"
    assert parsed["aweme_id"] == "7320876060210373923"


def test_parse_jingxuan_modal_id_url():
    # 精选页弹窗链接：/jingxuan?modal_id=xxx，应识别为单个作品
    url = "https://www.douyin.com/jingxuan?modal_id=7668679715758153713"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed["type"] == "video"
    assert parsed["aweme_id"] == "7668679715758153713"


def test_parse_modal_id_on_any_douyin_page():
    # modal_id 表示任意页面上弹窗打开的单个作品，均应优先按视频解析
    for path in ("discover", "search", "root", "user/MS4wLjABAAAA"):
        url = f"https://www.douyin.com/{path}?modal_id=7668679715758153713"
        parsed = URLParser.parse(url)
        assert parsed is not None, url
        assert parsed["type"] == "video", url
        assert parsed["aweme_id"] == "7668679715758153713", url


def test_extract_url_from_share_text():
    from utils.validators import extract_url_from_line

    line = "8.88 复制打开抖音，看看 https://v.douyin.com/ab12cd/ 的精彩内容"
    assert extract_url_from_line(line) == "https://v.douyin.com/ab12cd/"
    plain = "https://www.douyin.com/jingxuan?modal_id=7668679715758153713"
    assert extract_url_from_line(plain) == plain
    assert extract_url_from_line("这条没有链接") is None
    assert extract_url_from_line("") is None


def test_parse_gallery_url_sets_aweme_id():
    url = "https://www.douyin.com/note/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed["type"] == "gallery"
    assert parsed["aweme_id"] == "7320876060210373923"
    assert parsed["note_id"] == "7320876060210373923"


def test_parse_gallery_path_url_sets_aweme_id():
    url = "https://www.douyin.com/gallery/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed["type"] == "gallery"
    assert parsed["aweme_id"] == "7320876060210373923"
    assert parsed["note_id"] == "7320876060210373923"


def test_parse_collection_url_sets_mix_id():
    url = "https://www.douyin.com/collection/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed["type"] == "collection"
    assert parsed["mix_id"] == "7320876060210373923"


def test_parse_music_url_sets_music_id():
    url = "https://www.douyin.com/music/7320876060210373923"
    parsed = URLParser.parse(url)

    assert parsed is not None
    assert parsed["type"] == "music"
    assert parsed["music_id"] == "7320876060210373923"


def test_parse_unsupported_url_returns_none():
    url = "https://www.douyin.com/hashtag/123456"
    assert URLParser.parse(url) is None


def test_parse_short_url_marks_as_short():
    # 短链在 parser 层统一标记为 'short'，交由 CLI 预先解析真实链接。
    for url in (
        "https://v.douyin.com/ab12cd/",
        "http://v.douyin.com/ab12cd",
        "v.douyin.com/ab12cd",
        "https://v.iesdouyin.com/xyz789/",
    ):
        parsed = URLParser.parse(url)
        assert parsed is not None, url
        assert parsed["type"] == "short", url


def test_parse_live_url():
    parsed = URLParser.parse("https://live.douyin.com/123456789")
    assert parsed is not None
    assert parsed["type"] == "live"
    assert parsed["room_id"] == "123456789"

    parsed = URLParser.parse("https://www.douyin.com/follow/live/987654321")
    assert parsed is not None
    assert parsed["type"] == "live"
    assert parsed["room_id"] == "987654321"


def test_parse_live_replay_vsdetail_url():
    parsed = URLParser.parse("https://www.douyin.com/vsdetail/7331203341890049058")

    assert parsed is not None
    assert parsed["type"] == "live_replay"
    assert parsed["episode_id"] == "7331203341890049058"


def test_parse_live_replay_reflow_share_url():
    parsed = URLParser.parse(
        "https://webcast.amemv.com/douyin/webcast/reflow/episode/"
        "7331203341890049058?replay_id=7331203341890049058"
    )

    assert parsed is not None
    assert parsed["type"] == "live_replay"
    assert parsed["episode_id"] == "7331203341890049058"
