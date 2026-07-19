from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core.api_client import DouyinAPIClient
from core.mix_downloader import MixDownloader
from core.url_parser import URLParser
from core.user_downloader import UserDownloader
from core.user_modes.base_strategy import BaseUserModeStrategy
from storage import FileManager
from utils.validators import is_short_url, normalize_short_url


@dataclass
class PreviewItem:
    aweme_id: str
    title: str
    publish_time: str
    duration: str
    media_type: str
    author_name: str
    author_sec_uid: str
    size_text: str
    source_type: str
    collection_name: str = ""
    raw: Dict[str, Any] = None  # type: ignore[assignment]


@dataclass
class PreviewResult:
    source: str
    source_type: str
    author_name: str
    items: List[PreviewItem]


class PreviewService:
    def __init__(self, config: ConfigLoader, cookie_manager: CookieManager):
        self.config = config
        self.cookie_manager = cookie_manager
        self.api_client = DouyinAPIClient(
            config.get_cookies(),
            proxy=(config.get("proxy") or None),
        )
        self.file_manager = FileManager(config.get("path") or "./Downloaded")
        retry_times = int(config.get("retry_times") or 3)
        self.downloader = UserDownloader(
            config=config,
            api_client=self.api_client,
            file_manager=self.file_manager,
            cookie_manager=cookie_manager,
            database=None,
            rate_limiter=RateLimiter(),
            retry_handler=RetryHandler(max_retries=retry_times),
            queue_manager=QueueManager(max_workers=1),
        )

    async def close(self) -> None:
        await self.api_client.close()

    async def preview_url(self, url: str, mode: str = "post") -> PreviewResult:
        resolved_url = await self._resolve_url(url)
        parsed = URLParser.parse(resolved_url)
        if not parsed:
            raise RuntimeError(f"无法识别链接：{url}")

        url_type = parsed.get("type")
        if url_type in {"video", "gallery"}:
            aweme_id = str(parsed.get("aweme_id") or "")
            detail = await self.api_client.get_video_detail(aweme_id)
            if not detail:
                raise RuntimeError(f"获取作品详情失败：{aweme_id}")
            item = self._to_preview_item(detail, "单个作品")
            return PreviewResult(resolved_url, url_type, item.author_name, [item])

        if url_type == "user":
            return await self._preview_user(resolved_url, parsed, mode)

        if url_type == "collection":
            return await self._preview_collection(resolved_url, parsed)

        if url_type == "music":
            return await self._preview_music(resolved_url, parsed)

        if url_type == "live":
            room_id = str(parsed.get("room_id") or "")
            item = PreviewItem(
                aweme_id=room_id,
                title=f"直播间 {room_id}",
                publish_time="实时",
                duration="直播",
                media_type="直播",
                author_name="live",
                author_sec_uid="",
                size_text="未知",
                source_type="live",
                raw={"room_id": room_id, "preview_only": True},
            )
            return PreviewResult(resolved_url, url_type, "live", [item])

        raise RuntimeError(f"暂不支持预览此链接类型：{url_type}")

    async def _resolve_url(self, url: str) -> str:
        stripped = (url or "").strip()
        if not stripped:
            raise RuntimeError("链接为空")
        if is_short_url(stripped):
            resolved = await self.api_client.resolve_short_url(normalize_short_url(stripped))
            if not resolved:
                raise RuntimeError(f"短链接解析失败：{stripped}")
            return resolved
        return stripped

    async def _preview_user(
        self, source: str, parsed: Dict[str, Any], mode: str
    ) -> PreviewResult:
        sec_uid = str(parsed.get("sec_uid") or "")
        modes = [mode or "post"]
        user_info = await self.downloader._resolve_user_info(sec_uid, modes)
        if not user_info:
            raise RuntimeError("获取用户信息失败，请检查 Cookie 是否有效或重新登录抖音")

        strategy = self.downloader._get_mode_strategy(mode)
        if not strategy:
            raise RuntimeError(f"不支持的主页模式：{mode}")
        items = await strategy.collect_items(sec_uid, user_info)
        items = strategy.apply_filters(items)
        author_name = user_info.get("nickname") or "unknown"
        return PreviewResult(
            source=source,
            source_type=f"user:{mode}",
            author_name=author_name,
            items=self._dedupe_preview_items(items, author_name, f"user:{mode}"),
        )

    async def _preview_collection(
        self, source: str, parsed: Dict[str, Any]
    ) -> PreviewResult:
        mix_id = str(parsed.get("mix_id") or "")
        downloader = MixDownloader(
            config=self.config,
            api_client=self.api_client,
            file_manager=self.file_manager,
            cookie_manager=self.cookie_manager,
            database=None,
            rate_limiter=RateLimiter(),
            retry_handler=RetryHandler(max_retries=int(self.config.get("retry_times") or 3)),
            queue_manager=QueueManager(max_workers=1),
        )
        detail = await downloader._get_mix_detail(mix_id)
        author_name = (
            (detail.get("author") or {}).get("nickname") if isinstance(detail, dict) else None
        ) or "mix"
        items = await downloader._collect_mix_aweme_list(mix_id)
        return PreviewResult(
            source=source,
            source_type="collection",
            author_name=author_name,
            items=self._dedupe_preview_items(items, author_name, "collection"),
        )

    async def _preview_music(self, source: str, parsed: Dict[str, Any]) -> PreviewResult:
        music_id = str(parsed.get("music_id") or "")
        detail = await self.api_client.get_music_detail(music_id)
        author_name = "music"
        if isinstance(detail, dict):
            author_name = (
                detail.get("author_name")
                or (detail.get("owner") or {}).get("nickname")
                or detail.get("title")
                or "music"
            )
        items: List[Dict[str, Any]] = []
        cursor = 0
        has_more = True
        limit = int((self.config.get("number") or {}).get("music") or 0)
        while has_more:
            await self.downloader.rate_limiter.acquire()
            page_data = await self.api_client.get_music_aweme(music_id, cursor=cursor, count=20)
            page = BaseUserModeStrategy._normalize_page_data(page_data)
            page_items = [
                item
                for item in page.get("items", [])
                if isinstance(item, dict) and item.get("aweme_id")
            ]
            if not page_items:
                break
            items.extend(page_items)
            if limit > 0 and len(items) >= limit:
                items = items[:limit]
                break
            has_more = bool(page.get("has_more", False))
            next_cursor = int(page.get("max_cursor", 0) or 0)
            if has_more and next_cursor == cursor:
                break
            cursor = next_cursor
        return PreviewResult(
            source=source,
            source_type="music",
            author_name=author_name,
            items=self._dedupe_preview_items(items, author_name, "music"),
        )

    def _dedupe_preview_items(
        self, items: List[Dict[str, Any]], author_name: str, source_type: str
    ) -> List[PreviewItem]:
        seen: set[str] = set()
        preview_items: List[PreviewItem] = []
        for item in items:
            aweme_id = str(item.get("aweme_id") or "")
            if not aweme_id or aweme_id in seen:
                continue
            seen.add(aweme_id)
            preview_items.append(self._to_preview_item(item, source_type, author_name))
        return preview_items

    def _to_preview_item(
        self, aweme: Dict[str, Any], source_type: str, author_name: Optional[str] = None
    ) -> PreviewItem:
        author = aweme.get("author") or {}
        nickname = author_name or author.get("nickname") or "unknown"
        create_time = self._format_timestamp(aweme.get("create_time"))
        duration = self._format_duration((aweme.get("video") or {}).get("duration"))
        media_type = self._media_type_label(self.downloader._detect_media_type(aweme))
        # Extract collection name from mix_info
        collection = ""
        mix_info = aweme.get("mix_info") if isinstance(aweme, dict) else None
        if isinstance(mix_info, dict):
            collection = (mix_info.get("mix_name") or mix_info.get("name") or "").strip()
        return PreviewItem(
            aweme_id=str(aweme.get("aweme_id") or ""),
            title=(aweme.get("desc") or "无标题").strip() or "无标题",
            publish_time=create_time,
            duration=duration,
            media_type=media_type,
            author_name=nickname,
            author_sec_uid=str(author.get("sec_uid") or ""),
            size_text="未知",
            source_type=source_type,
            collection_name=collection,
            raw=aweme,
        )

    @staticmethod
    def _format_timestamp(value: Any) -> str:
        try:
            timestamp = int(value or 0)
        except (TypeError, ValueError):
            timestamp = 0
        if timestamp <= 0:
            return "未知"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))

    @staticmethod
    def _format_duration(value: Any) -> str:
        try:
            ms = int(value or 0)
        except (TypeError, ValueError):
            ms = 0
        if ms <= 0:
            return "未知"
        seconds = max(1, round(ms / 1000))
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    @staticmethod
    def _media_type_label(media_type: str) -> str:
        return {
            "video": "视频",
            "gallery": "图文",
            "music": "音乐",
        }.get(media_type, media_type or "未知")
