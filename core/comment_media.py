"""评论区图片/动图媒体提取与下载。

抖音评论接口中图片字段（``image_list`` 内每一项）通常同时带四档地址：
``origin_url``（无水印原图）→ ``download_url`` → ``medium_url`` →
``thumb_url``。下载时按该顺序回退，保证默认拿到原图。

评论区动图（live photo）表现为“静态图 + 视频”：静态图仍是 image_list
的一项，视频挂在同一项的 ``video_list`` / ``video`` 下。下载后调用
``core.live_photo.merge_live_photo_files`` 合并为可导入手机的动态照片。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.live_photo import LIVE_MERGED_DIR_NAME, LIVE_RAW_DIR_NAME, merge_live_photo_files
from utils.logger import setup_logger

if TYPE_CHECKING:  # pragma: no cover
    from core.api_client import DouyinAPIClient
    from storage.file_manager import FileManager

logger = setup_logger("CommentMedia")


@dataclass
class CommentImage:
    """一条评论中的一张图片（可能是动图）。"""

    comment_id: str
    index: int
    urls: List[str] = field(default_factory=list)          # 原图优先的镜像列表
    live_video_urls: List[str] = field(default_factory=list)
    preview_url: str = ""                                   # 缩略预览地址
    width: int = 0
    height: int = 0

    @property
    def is_live(self) -> bool:
        return bool(self.live_video_urls)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comment_id": self.comment_id,
            "index": self.index,
            "urls": self.urls,
            "live_video_urls": self.live_video_urls,
            "preview_url": self.preview_url,
            "width": self.width,
            "height": self.height,
            "is_live": self.is_live,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommentImage":
        return cls(
            comment_id=str(data.get("comment_id") or ""),
            index=int(data.get("index") or 0),
            urls=list(data.get("urls") or []),
            live_video_urls=list(data.get("live_video_urls") or []),
            preview_url=str(data.get("preview_url") or ""),
            width=int(data.get("width") or 0),
            height=int(data.get("height") or 0),
        )


def _extract_urls(source: Any) -> List[str]:
    """从 ``{url_list: [...]}`` / list / str 中提取 URL 列表。"""
    if isinstance(source, dict):
        for key in ("url_list", "urlList"):
            value = source.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, str) and item]
        return []
    if isinstance(source, list):
        return [item for item in source if isinstance(item, str) and item]
    if isinstance(source, str) and source:
        return [source]
    return []


def _positive_int(value: Any) -> int:
    try:
        number = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _dedupe(values: List[str]) -> List[str]:
    seen: set = set()
    result: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


_WATERMARK_HINTS = (
    "tplv-dy-water",
    "dy-water",
    "owner_watermark",
    "watermark_image",
    "watermark=1",
    "playwm",
)


def _is_watermarked_url(url: str) -> bool:
    normalized = str(url or "").lower()
    return any(hint in normalized for hint in _WATERMARK_HINTS)


def _ranked_image_urls(item: Dict[str, Any]) -> List[str]:
    """按 原图→下载→中等→缩略 顺序收集镜像，始终优先无水印 URL。"""
    urls: List[str] = []
    for key in ("watermark_free_download_url_list", "origin_image", "origin_url",
                "display_image", "download_url", "medium_url", "thumb_url"):
        urls.extend(_extract_urls(item.get(key)))
    urls.extend(_extract_urls(item.get("download_url_list")))
    urls.extend(_extract_urls(item.get("url_list")))
    urls.extend(_extract_urls(item.get("owner_watermark_image")))
    deduped = _dedupe(urls)
    watermark_free = [u for u in deduped if not _is_watermarked_url(u)]
    watermarked = [u for u in deduped if _is_watermarked_url(u)]
    return watermark_free + watermarked


def _extract_bit_rate_play_urls(video: Dict[str, Any]) -> List[str]:
    bit_rate = video.get("bit_rate")
    if not isinstance(bit_rate, list):
        return []
    scored = []
    for entry in bit_rate:
        if not isinstance(entry, dict):
            continue
        br = _positive_int(entry.get("bit_rate"))
        urls = _extract_urls(entry.get("play_addr"))
        if urls:
            scored.append((br, urls))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    result: List[str] = []
    for _, urls in scored:
        result.extend(urls)
    return result


def _live_video_urls(item: Dict[str, Any]) -> List[str]:
    """收集动图视频源：``video_list`` / ``video`` / 平铺字段，无水印 ``play_addr`` 优先。"""
    preferred: List[str] = []
    fallback: List[str] = []
    video_list = item.get("video_list")
    if isinstance(video_list, list):
        for entry in video_list:
            if isinstance(entry, dict):
                preferred.extend(_extract_bit_rate_play_urls(entry))
                preferred.extend(_extract_urls(entry.get("play_addr")))
                preferred.extend(_extract_urls(entry.get("url_list")))
                fallback.extend(_extract_urls(entry.get("download_addr")))
            else:
                preferred.extend(_extract_urls(entry))
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    if video:
        preferred.extend(_extract_bit_rate_play_urls(video))
        for key in ("play_addr", "play_addr_h264", "play_addr_265", "play_addr_256", "url_list"):
            preferred.extend(_extract_urls(video.get(key)))
        fallback.extend(_extract_urls(video.get("download_addr")))
    preferred.extend(_extract_urls(item.get("video_play_addr")))
    fallback.extend(_extract_urls(item.get("video_download_addr")))
    deduped = _dedupe(preferred + fallback)
    watermark_free = [u for u in deduped if not _is_watermarked_url(u)]
    watermarked = [u for u in deduped if _is_watermarked_url(u)]
    return watermark_free + watermarked


def extract_comment_images(comment: Dict[str, Any]) -> List[CommentImage]:
    """从一条评论中提取图片（含动图信息）。"""
    comment_id = str(comment.get("cid") or comment.get("comment_id") or "")
    image_list = comment.get("image_list") or []
    if not isinstance(image_list, list):
        return []

    images: List[CommentImage] = []
    for index, item in enumerate(image_list):
        if not isinstance(item, dict):
            continue
        urls = _ranked_image_urls(item)
        if not urls:
            continue
        live_urls = _live_video_urls(item)
        thumb_url = _extract_first(item.get("thumb_url")) or urls[-1]
        images.append(
            CommentImage(
                comment_id=comment_id,
                index=index,
                urls=urls,
                live_video_urls=live_urls,
                preview_url=thumb_url,
                width=_positive_int(item.get("width") or item.get("w")),
                height=_positive_int(item.get("height") or item.get("h")),
            )
        )
    return images


def _extract_first(source: Any) -> str:
    urls = _extract_urls(source)
    return urls[0] if urls else ""


def collect_all_comment_images(comments: List[Dict[str, Any]]) -> List[CommentImage]:
    """扁平化收集多条评论的全部图片。"""
    images: List[CommentImage] = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        images.extend(extract_comment_images(comment))
        replies = comment.get("_replies")
        if isinstance(replies, list):
            for reply in replies:
                if isinstance(reply, dict):
                    images.extend(extract_comment_images(reply))
    return images


class CommentMediaDownloader:
    """评论图片/动图下载器：原图优先、多镜像回退、动图自动合并。"""

    def __init__(
        self,
        file_manager: "FileManager",
        api_client: "DouyinAPIClient",
        *,
        retry_handler=None,
        headers: Optional[Dict[str, str]] = None,
    ):
        from control import RetryHandler

        self.file_manager = file_manager
        self.api_client = api_client
        self.retry_handler = retry_handler or RetryHandler(max_retries=3)
        self.proxy = getattr(api_client, "proxy", None) or None
        self.headers = headers or {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
        }

    async def download_image(
        self,
        image: CommentImage,
        save_dir: Path,
        stem: str,
    ) -> Optional[Path]:
        """下载一张图片（原图优先），返回保存路径或 None。"""
        urls = image.urls or ([image.preview_url] if image.preview_url else [])
        if not urls:
            logger.warning("Comment image %s has no URL", stem)
            return None
        suffix = infer_image_extension(urls[0])
        save_path = Path(save_dir) / f"{stem}{suffix}"
        return await self._download_first_available(urls, save_path)

    async def download_live_photo(
        self,
        image: CommentImage,
        save_dir: Path,
        stem: str,
        *,
        merge: bool = True,
        format_mode: str = "universal",
    ) -> Dict[str, Optional[Path]]:
        """下载动图：原始静图+视频存入 ``实况素材/``，合成动态图以同主文件名存入 ``合成动图/``。"""
        base_dir = Path(save_dir)
        raw_dir = base_dir / LIVE_RAW_DIR_NAME
        raw_dir.mkdir(parents=True, exist_ok=True)
        still = await self.download_image(image, raw_dir, stem)

        video: Optional[Path] = None
        if image.live_video_urls:
            video_path = raw_dir / f"{stem}.mp4"
            video = await self._download_first_available(image.live_video_urls, video_path)

        merged: Optional[Path] = None
        if merge and still and video:
            merged_dir = base_dir / LIVE_MERGED_DIR_NAME
            merged_dir.mkdir(parents=True, exist_ok=True)
            merged_path = merged_dir / f"{stem}.jpg"
            merged = merge_live_photo_files(
                still, video, merged_path, format_mode=format_mode
            )
        return {"image": still, "video": video, "merged": merged}

    async def download_comment_images(
        self,
        images: List[CommentImage],
        save_dir: Path,
        *,
        progress_callback=None,
        merge_live: bool = True,
        live_photo_format: str = "universal",
    ) -> Dict[str, Any]:
        """批量下载，返回 {"success": [...], "failed": [...]} 路径列表。"""
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        success: List[Path] = []
        failed: List[CommentImage] = []
        total = len(images)
        for index, image in enumerate(images, start=1):
            stem = f"{image.comment_id}_{image.index + 1}"
            try:
                if image.is_live:
                    result = await self.download_live_photo(
                        image,
                        save_dir,
                        stem,
                        merge=merge_live,
                        format_mode=live_photo_format,
                    )
                    merged = result.get("merged")
                    if merged:
                        success.append(merged)
                        if result.get("image"):
                            success.append(result["image"])
                        if result.get("video"):
                            success.append(result["video"])
                    elif result.get("image") or result.get("video"):
                        # 合并失败时保留原始素材
                        for path in (result.get("image"), result.get("video")):
                            if path:
                                success.append(path)
                    else:
                        failed.append(image)
                else:
                    path = await self.download_image(image, save_dir, stem)
                    if path:
                        success.append(path)
                    else:
                        failed.append(image)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Comment image download failed %s: %s", stem, exc)
                failed.append(image)
            if progress_callback:
                progress_callback(index, total, len(success), len(failed), stem)
        return {"success": success, "failed": failed}

    async def download_preview(self, url: str, save_path: Path) -> Optional[Path]:
        """下载缩略图/预览图（单次尝试，失败静默）。"""
        result = await self._download(
            url,
            save_path,
            optional=True,
            retry=False,
            prefer_response_content_type=True,
        )
        return Path(result) if result else None

    async def _download_first_available(self, urls: List[str], save_path: Path) -> Optional[Path]:
        use_backoff = len(urls) == 1
        for index, url in enumerate(urls):
            is_last = index == len(urls) - 1
            result = await self._download(
                url,
                save_path,
                optional=not is_last,
                retry=use_backoff,
                prefer_response_content_type=True,
            )
            if result:
                return Path(result)
        return None

    async def _download(
        self,
        url: str,
        save_path: Path,
        *,
        optional: bool = False,
        retry: bool = True,
        prefer_response_content_type: bool = False,
    ):
        session = await self.api_client.get_session()

        async def _task():
            result = await self.file_manager.download_file(
                url,
                save_path,
                session,
                headers=self.headers,
                proxy=self.proxy,
                prefer_response_content_type=prefer_response_content_type,
                return_saved_path=True,
            )
            if not result:
                raise RuntimeError(f"Download failed for {save_path.name}")
            return result

        try:
            if retry:
                return await self.retry_handler.execute_with_retry(_task)
            return await _task()
        except Exception as exc:  # noqa: BLE001
            log_fn = logger.warning if optional else logger.error
            log_fn("Comment media download error %s: %s", save_path.name, exc)
            return False


def infer_image_extension(image_url: str) -> str:
    """根据 URL 推断图片扩展名，缺省 .jpg。"""
    from urllib.parse import urlparse

    allowed = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if not image_url:
        return ".jpg"
    path = (urlparse(image_url).path or "").lower()
    raw_suffix = Path(path).suffix.lower()
    if raw_suffix in allowed:
        return raw_suffix
    import re

    matches = re.findall(r"\.(?:jpe?g|png|webp|gif)(?=[^a-z0-9]|$)", path)
    if matches:
        return matches[-1].lower()
    return ".jpg"
