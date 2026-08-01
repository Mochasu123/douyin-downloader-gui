"""评论图片/动图提取与下载测试。"""

from pathlib import Path

import pytest

from core.comment_media import (
    CommentImage,
    CommentMediaDownloader,
    collect_all_comment_images,
    extract_comment_images,
)


def _comment_with_images():
    return {
        "cid": "C1",
        "text": "看看这张图",
        "image_list": [
            {
                "origin_url": {"url_list": ["https://cdn/origin-1.webp"]},
                "download_url": {"url_list": ["https://cdn/download-1.webp"]},
                "medium_url": {"url_list": ["https://cdn/medium-1.webp"]},
                "thumb_url": {"url_list": ["https://cdn/thumb-1.webp"]},
                "width": 1080,
                "height": 1920,
            },
            {
                "origin_url": "https://cdn/live-origin.jpg",
                "thumb_url": "https://cdn/live-thumb.jpg",
                "video_list": [
                    {"play_addr": {"url_list": ["https://cdn/live-video-1.mp4"]}}
                ],
            },
        ],
    }


def test_extract_comment_images_ranks_original_first():
    images = extract_comment_images(_comment_with_images())
    assert len(images) == 2
    first = images[0]
    assert first.urls == [
        "https://cdn/origin-1.webp",
        "https://cdn/download-1.webp",
        "https://cdn/medium-1.webp",
        "https://cdn/thumb-1.webp",
    ]
    assert first.preview_url == "https://cdn/thumb-1.webp"
    assert first.width == 1080
    assert first.height == 1920
    assert first.is_live is False


def test_extract_comment_images_detects_live_photo():
    images = extract_comment_images(_comment_with_images())
    second = images[1]
    assert second.is_live is True
    assert second.live_video_urls == ["https://cdn/live-video-1.mp4"]
    assert second.urls == [
        "https://cdn/live-origin.jpg",
        "https://cdn/live-thumb.jpg",
    ]


def test_extract_comment_images_empty_and_missing():
    assert extract_comment_images({"cid": "X"}) == []
    assert extract_comment_images({"cid": "X", "image_list": []}) == []
    assert extract_comment_images({"cid": "X", "image_list": [{"thumb_url": ""}]}) == []


def test_collect_all_comment_images_includes_replies():
    comment = _comment_with_images()
    comment["_replies"] = [
        {
            "cid": "R1",
            "image_list": [{"origin_url": {"url_list": ["https://cdn/reply-1.jpg"]}}],
        }
    ]
    images = collect_all_comment_images([comment])
    assert len(images) == 3
    assert images[2].comment_id == "R1"


def test_comment_image_roundtrip_dict():
    image = extract_comment_images(_comment_with_images())[0]
    restored = CommentImage.from_dict(image.to_dict())
    assert restored.urls == image.urls
    assert restored.comment_id == "C1"


class _FakeFileManager:
    def __init__(self, result=True):
        self.result = result
        self.calls = []

    async def download_file(self, url, save_path, session, **kwargs):
        self.calls.append(url)
        if self.result:
            Path(save_path).write_bytes(b"data")
            return save_path
        return False


class _FakeAPIClient:
    proxy = None

    async def get_session(self):
        return "session"


def _downloader(fake_fm=None):
    from control import RetryHandler

    return CommentMediaDownloader(
        fake_fm or _FakeFileManager(),
        _FakeAPIClient(),
        retry_handler=RetryHandler(max_retries=0),
    )


@pytest.mark.asyncio
async def test_download_image_uses_first_available(tmp_path):
    fm = _FakeFileManager()
    image = extract_comment_images(_comment_with_images())[0]
    path = await _downloader(fm).download_image(image, tmp_path, "pic")
    assert path == tmp_path / "pic.webp"
    assert path.exists()
    assert fm.calls[0] == "https://cdn/origin-1.webp"


@pytest.mark.asyncio
async def test_download_image_falls_back_across_mirrors(tmp_path):
    fm = _FakeFileManager()
    fm.result = False

    class _FlakyFM(_FakeFileManager):
        async def download_file(self, url, save_path, session, **kwargs):
            self.calls.append(url)
            if url == "https://cdn/medium-1.webp":
                Path(save_path).write_bytes(b"data")
                return save_path
            return False

    image = extract_comment_images(_comment_with_images())[0]
    path = await _downloader(_FlakyFM()).download_image(image, tmp_path, "pic")
    assert path == tmp_path / "pic.webp"


@pytest.mark.asyncio
async def test_download_image_failure_returns_none(tmp_path):
    fm = _FakeFileManager(result=False)
    image = extract_comment_images(_comment_with_images())[0]
    path = await _downloader(fm).download_image(image, tmp_path, "pic")
    assert path is None


@pytest.mark.asyncio
async def test_download_live_photo_merges(tmp_path):
    image = extract_comment_images(_comment_with_images())[1]
    result = await _downloader().download_live_photo(image, tmp_path, "live")
    assert result["image"] == tmp_path / "live.jpg"
    assert result["video"] == tmp_path / "live_live.mp4"
    assert result["merged"] == tmp_path / "live_live.jpg"
    assert result["merged"].exists()
    data = result["merged"].read_bytes()
    assert data.endswith(b"LIVE_000000000000004")


@pytest.mark.asyncio
async def test_download_comment_images_reports_progress(tmp_path):
    images = extract_comment_images(_comment_with_images())
    events = []

    def progress(current, total, success, failed, name):
        events.append((current, total, success, failed))

    result = await _downloader().download_comment_images(
        images, tmp_path, progress_callback=progress)
    assert len(result["success"]) == 4  # 2 张静态图 + 1 动图（图+视频+合并）
    assert result["failed"] == []
    assert events == [(1, 2, 1, 0), (2, 2, 4, 0)]
