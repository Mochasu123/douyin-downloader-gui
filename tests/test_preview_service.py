"""预览服务：链接分类与直播/回放拒绝逻辑测试。"""

import asyncio

import pytest

from auth import CookieManager
from config import ConfigLoader
from core.preview_service import PreviewService, UnsupportedLinkError


def _service(tmp_path):
    return PreviewService(ConfigLoader(), CookieManager(str(tmp_path / "cookies.json")))


def test_classify_url_video(tmp_path):
    resolved, parsed = asyncio.run(_service(tmp_path).classify_url(
        "https://www.douyin.com/video/1234567890123456789"))
    assert parsed["type"] == "video"
    assert parsed["aweme_id"] == "1234567890123456789"


def test_classify_url_extracts_share_text(tmp_path):
    resolved, parsed = asyncio.run(_service(tmp_path).classify_url(
        "8.88 复制打开抖音 https://www.douyin.com/video/1234567890123456789 看看"))
    assert parsed["type"] == "video"
    assert parsed["aweme_id"] == "1234567890123456789"


def test_preview_rejects_live_link(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(UnsupportedLinkError):
        asyncio.run(service.preview_url("https://live.douyin.com/123456789"))
    with pytest.raises(UnsupportedLinkError):
        asyncio.run(service.preview_url("https://www.douyin.com/follow/live/987654321"))


def test_preview_rejects_live_replay_link(tmp_path):
    service = _service(tmp_path)
    with pytest.raises(UnsupportedLinkError):
        asyncio.run(service.preview_url(
            "https://www.douyin.com/vsdetail/7331203341890049058"))
