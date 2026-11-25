"""预览服务：链接分类、DRM 放映厅拒绝及直播/回放/视频预览测试。"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from auth import CookieManager
from config import ConfigLoader
from core.preview_service import PreviewService, UnsupportedLinkError


def _service(tmp_path):
    return PreviewService(ConfigLoader(), CookieManager(str(tmp_path / "cookies.json")))


def test_classify_url_video(tmp_path):
    service = _service(tmp_path)
    try:
        resolved, parsed = asyncio.run(
            service.classify_url("https://www.douyin.com/video/1234567890123456789")
        )
        assert parsed["type"] == "video"
        assert parsed["aweme_id"] == "1234567890123456789"
    finally:
        asyncio.run(service.close())


def test_classify_url_extracts_share_text(tmp_path):
    service = _service(tmp_path)
    try:
        resolved, parsed = asyncio.run(
            service.classify_url(
                "8.88 复制打开抖音 https://www.douyin.com/video/1234567890123456789 看看"
            )
        )
        assert parsed["type"] == "video"
        assert parsed["aweme_id"] == "1234567890123456789"
    finally:
        asyncio.run(service.close())


def test_preview_rejects_lvdetail_drm(tmp_path):
    service = _service(tmp_path)
    try:
        with pytest.raises(UnsupportedLinkError):
            asyncio.run(service.preview_url("https://www.douyin.com/lvdetail/7331203341890049058"))
    finally:
        asyncio.run(service.close())


def test_preview_live_link_returns_item(tmp_path):
    service = _service(tmp_path)
    service.api_client.get_live_room_info = AsyncMock(
        return_value={
            "room": {"title": "测试直播间", "status": 2},
            "user": {"nickname": "主播A", "sec_uid": "sec_anchor"},
        }
    )
    try:
        result = asyncio.run(service.preview_url("https://live.douyin.com/123456789"))
        assert result.source_type == "live"
        assert result.author_name == "主播A"
        assert len(result.items) == 1
        assert result.items[0].media_type == "直播"
        assert "测试直播间" in result.items[0].title
    finally:
        asyncio.run(service.close())


def test_preview_live_replay_link_returns_item(tmp_path):
    service = _service(tmp_path)
    service.api_client.get_live_replay_episode = AsyncMock(
        return_value={
            "title": "精彩回放",
            "duration": 125,
            "create_time": 1700000000,
            "owner": {"nickname": "主播B", "sec_uid": "sec_b"},
        }
    )
    try:
        result = asyncio.run(
            service.preview_url("https://www.douyin.com/vsdetail/7331203341890049058")
        )
        assert result.source_type == "live_replay"
        assert result.author_name == "主播B"
        assert len(result.items) == 1
        assert result.items[0].media_type == "直播回放"
        assert result.items[0].duration == "02:05"
    finally:
        asyncio.run(service.close())
