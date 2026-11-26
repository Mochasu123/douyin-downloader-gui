from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core.api_client import DouyinAPIClient
from core.downloader_factory import UNSUPPORTED_URL_TYPE_DETAIL
from core.metadata import extract_video_cover_urls
from core.mix_downloader import MixDownloader
from core.url_parser import URLParser
from core.user_downloader import UserDownloader
from core.user_modes.base_strategy import BaseUserModeStrategy
from storage import FileManager
from utils.validators import extract_url_from_line, is_short_url, normalize_short_url


class UnsupportedLinkError(RuntimeError):
    """链接类型已识别，但当前平台能力不支持（如放映厅加密影视）。"""


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
    cover_url: str = ""
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    is_live_photo: bool = False
    image_count: int = 0
    resolution: str = ""
    share_url: str = ""
    author_avatar_url: str = ""
    create_time: int = 0
    duration_ms: int = 0

    def to_summary_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


@dataclass
class PreviewResult:
    source: str
    source_type: str
    author_name: str
    items: List[PreviewItem]
    avatar_url: str = ""
    sec_uid: str = ""
    signature: str = ""
    follower_count: int = 0
    aweme_count: int = 0
    url_type: str = ""


OnItemCallback = Optional[Callable[[PreviewItem], Awaitable[None] | None]]


class PreviewService:
    def __init__(
        self,
        config: ConfigLoader,
        cookie_manager: CookieManager,
        *,
        page_bridge: Optional[Any] = None,
    ):
        self.config = config
        self.cookie_manager = cookie_manager
        self.api_client = DouyinAPIClient(
            config.get_cookies(),
            proxy=(config.get("proxy") or None),
            page_bridge=page_bridge,
        )
        self.file_manager = FileManager(config.get("path") or "./Downloaded")
        retry_times = int(config.get("retry_times") or 3)
        self.downloader = UserDownloader(
            config=config,
            api_client=self.api_client,
            file_manager=self.file_manager,
            cookie_manager=cookie_manager,
            database=None,
            rate_limiter=RateLimiter(max_per_second=float(config.get("rate_limit", 2) or 2)),
            retry_handler=RetryHandler(max_retries=retry_times),
            queue_manager=QueueManager(max_workers=1),
        )

    async def close(self) -> None:
        await self.api_client.close()

    async def preview_url(
        self,
        url: str,
        mode: str = "post",
        *,
        on_item: OnItemCallback = None,
    ) -> PreviewResult:
        resolved_url, parsed = await self.classify_url(url)

        url_type = parsed.get("type")
        if url_type in UNSUPPORTED_URL_TYPE_DETAIL:
            raise UnsupportedLinkError(UNSUPPORTED_URL_TYPE_DETAIL[url_type])

        if url_type in {"video", "gallery"}:
            aweme_id = str(parsed.get("aweme_id") or "")
            detail = await self.api_client.get_video_detail(aweme_id)
            if not detail:
                raise RuntimeError(f"获取作品详情失败：{aweme_id}")
            item = self._to_preview_item(detail, "单个作品")
            await self._emit_item(on_item, item)
            return PreviewResult(
                source=resolved_url,
                source_type=url_type,
                author_name=item.author_name,
                items=[item],
                avatar_url=item.author_avatar_url,
                sec_uid=item.author_sec_uid,
                url_type=url_type,
            )

        if url_type == "live":
            return await self._preview_live(resolved_url, parsed, on_item=on_item)

        if url_type == "live_replay":
            return await self._preview_live_replay(resolved_url, parsed, on_item=on_item)

        if url_type == "user":
            return await self._preview_user(resolved_url, parsed, mode, on_item=on_item)

        if url_type == "collection":
            return await self._preview_collection(resolved_url, parsed, on_item=on_item)

        if url_type == "music":
            return await self._preview_music(resolved_url, parsed, on_item=on_item)

        raise RuntimeError(f"暂不支持预览此链接类型：{url_type}")

    async def classify_url(self, url: str):
        """解析短链并识别链接类型，返回 (resolved_url, parsed)。"""
        resolved_url = await self._resolve_url(url)
        parsed = URLParser.parse(resolved_url)
        if not parsed:
            raise RuntimeError(f"无法识别链接：{url}")
        return resolved_url, parsed

    async def _resolve_url(self, url: str) -> str:
        stripped = (url or "").strip()
        if not stripped:
            raise RuntimeError("链接为空")
        if stripped.lower() == "self":
            return "https://www.douyin.com/user/self"
        extracted = extract_url_from_line(stripped)
        if extracted:
            stripped = extracted
        if is_short_url(stripped):
            resolved = await self.api_client.resolve_short_url(normalize_short_url(stripped))
            if not resolved:
                raise RuntimeError(f"短链接解析失败：{stripped}")
            return resolved
        return stripped

    async def _preview_live(
        self, source: str, parsed: Dict[str, Any], *, on_item: OnItemCallback = None
    ) -> PreviewResult:
        room_id = str(parsed.get("room_id") or "")
        kwargs: Dict[str, Any] = {}
        if parsed.get("room_id_kind") == "room_id":
            kwargs = {
                "room_id_kind": "room_id",
                "sec_user_id": str(parsed.get("sec_user_id") or ""),
            }
        info = await self.api_client.get_live_room_info(room_id, **kwargs)
        room = (info or {}).get("room") or {}
        owner = (info or {}).get("user") or room.get("owner") or {}
        author_name = str(owner.get("nickname") or "主播")
        title = str(room.get("title") or f"直播间 {room_id}")
        status_code = str(room.get("status") or "")
        status_suffix = "（直播中）" if status_code == "2" else "（未开播/状态未知）"
        cover_url = self._first_url(room.get("cover")) or self._first_url(owner.get("avatar_thumb"))
        avatar_url = self._first_url(owner.get("avatar_larger")) or self._first_url(
            owner.get("avatar_thumb")
        )
        item = PreviewItem(
            aweme_id=f"live:{room_id}",
            title=f"{title} {status_suffix}".strip(),
            publish_time=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            duration="直播",
            media_type="直播",
            author_name=author_name,
            author_sec_uid=str(owner.get("sec_uid") or ""),
            size_text="流媒体",
            source_type="live",
            raw={"_kind": "live", "parsed": parsed, "info": info or {}},
            cover_url=cover_url,
            share_url=source,
            author_avatar_url=avatar_url,
        )
        await self._emit_item(on_item, item)
        return PreviewResult(
            source=source,
            source_type="live",
            author_name=author_name,
            items=[item],
            avatar_url=avatar_url,
            sec_uid=str(owner.get("sec_uid") or ""),
            url_type="live",
        )

    async def _preview_live_replay(
        self, source: str, parsed: Dict[str, Any], *, on_item: OnItemCallback = None
    ) -> PreviewResult:
        episode_id = str(parsed.get("episode_id") or "")
        episode = await self.api_client.get_live_replay_episode(episode_id)
        if not episode:
            raise RuntimeError(f"获取直播回放信息失败：{episode_id}")
        owner = episode.get("owner") or episode.get("anchor") or {}
        author_name = str(owner.get("nickname") or "主播")
        title = str(episode.get("title") or f"直播回放 {episode_id}")
        cover_url = self._first_url(episode.get("cover")) or self._first_url(
            owner.get("avatar_thumb")
        )
        avatar_url = self._first_url(owner.get("avatar_larger")) or self._first_url(
            owner.get("avatar_thumb")
        )
        duration_sec = int(episode.get("duration") or 0)
        duration_ms = duration_sec * 1000 if duration_sec > 0 else 0
        item = PreviewItem(
            aweme_id=f"live_replay:{episode_id}",
            title=title,
            publish_time=self._format_timestamp(episode.get("create_time")),
            duration=self._format_duration(duration_ms),
            media_type="直播回放",
            author_name=author_name,
            author_sec_uid=str(owner.get("sec_uid") or ""),
            size_text="未知",
            source_type="live_replay",
            raw={"_kind": "live_replay", "parsed": parsed, "episode": episode},
            cover_url=cover_url,
            share_url=source,
            author_avatar_url=avatar_url,
            create_time=int(episode.get("create_time") or 0),
            duration_ms=duration_ms,
        )
        await self._emit_item(on_item, item)
        return PreviewResult(
            source=source,
            source_type="live_replay",
            author_name=author_name,
            items=[item],
            avatar_url=avatar_url,
            sec_uid=str(owner.get("sec_uid") or ""),
            url_type="live_replay",
        )

    async def _preview_user(
        self,
        source: str,
        parsed: Dict[str, Any],
        mode: str,
        *,
        on_item: OnItemCallback = None,
    ) -> PreviewResult:
        sec_uid = str(parsed.get("sec_uid") or "")
        modes = [mode or "post"]
        sec_uid = await self.downloader._resolve_self_alias(sec_uid, modes)
        user_info = await self.downloader._resolve_user_info(sec_uid, modes)
        if not user_info:
            raise RuntimeError("获取用户信息失败，请检查 Cookie 是否有效或重新登录抖音")

        if mode in self.downloader.SELF_COLLECT_MODES and sec_uid != "self":
            self_info = await self.downloader.api_client.get_self_info()
            if not self_info or str(user_info.get("uid")) != str(self_info.get("uid")):
                raise RuntimeError("只能获取自己账号的收藏。请粘贴您自己的主页链接，或直接输入 self")
            sec_uid = "self"

        strategy = self.downloader._get_mode_strategy(mode)
        if not strategy:
            raise RuntimeError(f"不支持的主页模式：{mode}")
        raw_items = await strategy.collect_items(sec_uid, user_info)
        raw_items = strategy.apply_filters(raw_items)
        author_name = user_info.get("nickname") or "unknown"
        resolved_sec_uid = str(user_info.get("sec_uid") or sec_uid)
        avatar_url = self._first_url(user_info.get("avatar_larger")) or self._first_url(
            user_info.get("avatar_thumb")
        )
        items = await self._dedupe_and_emit(
            raw_items,
            author_name,
            f"user:{mode}",
            on_item=on_item,
            default_avatar=avatar_url,
        )
        return PreviewResult(
            source=source,
            source_type=f"user:{mode}",
            author_name=author_name,
            items=items,
            avatar_url=avatar_url,
            sec_uid=resolved_sec_uid,
            signature=str(user_info.get("signature") or ""),
            follower_count=int(user_info.get("follower_count") or 0),
            aweme_count=int(user_info.get("aweme_count") or 0),
            url_type="user",
        )

    @staticmethod
    def _first_url(source: Any) -> str:
        if isinstance(source, dict):
            url_list = source.get("url_list") or source.get("urlList") or []
            if url_list:
                return str(url_list[0])
        elif isinstance(source, list) and source:
            return str(source[0])
        elif isinstance(source, str):
            return source
        return ""

    async def _preview_collection(
        self,
        source: str,
        parsed: Dict[str, Any],
        *,
        on_item: OnItemCallback = None,
    ) -> PreviewResult:
        mix_id = str(parsed.get("mix_id") or "")
        downloader = MixDownloader(
            config=self.config,
            api_client=self.api_client,
            file_manager=self.file_manager,
            cookie_manager=self.cookie_manager,
            database=None,
            rate_limiter=self.downloader.rate_limiter,
            retry_handler=RetryHandler(max_retries=int(self.config.get("retry_times") or 3)),
            queue_manager=QueueManager(max_workers=1),
        )
        detail = await downloader._get_mix_detail(mix_id)
        author = (detail.get("author") or {}) if isinstance(detail, dict) else {}
        author_name = author.get("nickname") or "mix"
        avatar_url = self._first_url(author.get("avatar_thumb"))
        raw_items = await downloader._collect_mix_aweme_list(mix_id)
        items = await self._dedupe_and_emit(
            raw_items,
            author_name,
            "collection",
            on_item=on_item,
            default_avatar=avatar_url,
        )
        return PreviewResult(
            source=source,
            source_type="collection",
            author_name=author_name,
            items=items,
            avatar_url=avatar_url,
            sec_uid=str(author.get("sec_uid") or ""),
            url_type="collection",
        )

    async def _preview_music(
        self,
        source: str,
        parsed: Dict[str, Any],
        *,
        on_item: OnItemCallback = None,
    ) -> PreviewResult:
        music_id = str(parsed.get("music_id") or "")
        detail = await self.api_client.get_music_detail(music_id)
        author_name = "music"
        avatar_url = ""
        if isinstance(detail, dict):
            author_name = (
                detail.get("author_name")
                or (detail.get("owner") or {}).get("nickname")
                or detail.get("title")
                or "music"
            )
            avatar_url = self._first_url(detail.get("cover_large")) or self._first_url(
                detail.get("cover_thumb")
            )
        raw_items: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        preview_items: List[PreviewItem] = []
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
            for item in page_items:
                aweme_id = str(item.get("aweme_id") or "")
                if not aweme_id or aweme_id in seen_ids:
                    continue
                seen_ids.add(aweme_id)
                raw_items.append(item)
                p_item = self._to_preview_item(item, "music", author_name)
                preview_items.append(p_item)
                await self._emit_item(on_item, p_item)
                if limit > 0 and len(preview_items) >= limit:
                    has_more = False
                    break
            if not has_more:
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
            items=preview_items,
            avatar_url=avatar_url,
            url_type="music",
        )

    async def _emit_item(self, on_item: OnItemCallback, item: PreviewItem) -> None:
        if on_item is None:
            return
        res = on_item(item)
        if hasattr(res, "__await__"):
            await res

    async def _dedupe_and_emit(
        self,
        items: List[Dict[str, Any]],
        author_name: str,
        source_type: str,
        *,
        on_item: OnItemCallback = None,
        default_avatar: str = "",
    ) -> List[PreviewItem]:
        seen: set[str] = set()
        preview_items: List[PreviewItem] = []
        for item in items:
            aweme_id = str(item.get("aweme_id") or "")
            if not aweme_id or aweme_id in seen:
                continue
            seen.add(aweme_id)
            p_item = self._to_preview_item(
                item, source_type, author_name, default_avatar=default_avatar
            )
            preview_items.append(p_item)
            await self._emit_item(on_item, p_item)
        return preview_items

    def _to_preview_item(
        self,
        aweme: Dict[str, Any],
        source_type: str,
        author_name: Optional[str] = None,
        *,
        default_avatar: str = "",
    ) -> PreviewItem:
        author = aweme.get("author") or {}
        nickname = author.get("nickname") or author_name or "unknown"
        create_ts = self._safe_int(aweme.get("create_time"))
        create_time = self._format_timestamp(create_ts)
        video = aweme.get("video") if isinstance(aweme.get("video"), dict) else {}
        duration_ms = self._safe_int(video.get("duration"))
        duration = self._format_duration(duration_ms)
        detected_type = self.downloader._detect_media_type(aweme)
        media_type = self._media_type_label(detected_type)

        # Cover URL & size estimation
        cover_url = ""
        gallery_items = self.downloader._iter_gallery_items(aweme)
        image_count = len(gallery_items) if detected_type == "gallery" else 0
        is_live_photo = False
        if detected_type == "gallery" and gallery_items:
            first_img = gallery_items[0] if isinstance(gallery_items[0], dict) else {}
            candidates = self.downloader._image_item_url_candidates(first_img)
            if candidates:
                cover_url = candidates[0]
            is_live_photo = bool(self.downloader._collect_image_live_urls(aweme))
        if not cover_url:
            cover_urls = extract_video_cover_urls(aweme)
            if cover_urls:
                cover_url = cover_urls[0]

        # Resolution & estimated size from preferred bit_rate/play_addr
        resolution = ""
        size_bytes = 0
        if detected_type == "video" and video:
            quality = str(self.config.get("video_quality") or "highest")
            play_addr = self.downloader._pick_preferred_play_addr(video, quality) or {}
            size_bytes = self._safe_int(play_addr.get("data_size"))
            w = self._safe_int(play_addr.get("width") or video.get("width"))
            h = self._safe_int(play_addr.get("height") or video.get("height"))
            if w and h:
                resolution = f"{min(w, h)}p"

        # Statistics
        stats = aweme.get("statistics") if isinstance(aweme.get("statistics"), dict) else {}
        like_count = self._safe_int(stats.get("digg_count"))
        comment_count = self._safe_int(stats.get("comment_count"))
        share_count = self._safe_int(stats.get("share_count"))
        collect_count = self._safe_int(stats.get("collect_count"))

        # Collection name
        collection = ""
        mix_info = aweme.get("mix_info") if isinstance(aweme, dict) else None
        if isinstance(mix_info, dict):
            collection = (mix_info.get("mix_name") or mix_info.get("name") or "").strip()

        aweme_id = str(aweme.get("aweme_id") or "")
        share_url = str(aweme.get("share_url") or "")
        if not share_url and aweme_id:
            share_url = (
                f"https://www.douyin.com/note/{aweme_id}"
                if detected_type == "gallery"
                else f"https://www.douyin.com/video/{aweme_id}"
            )
        author_avatar = self._first_url(author.get("avatar_thumb")) or default_avatar

        return PreviewItem(
            aweme_id=aweme_id,
            title=(aweme.get("desc") or "无标题").strip() or "无标题",
            publish_time=create_time,
            duration=duration,
            media_type=media_type,
            author_name=nickname,
            author_sec_uid=str(author.get("sec_uid") or ""),
            size_text=self._human_size(size_bytes),
            source_type=source_type,
            collection_name=collection,
            raw=aweme,
            cover_url=cover_url,
            like_count=like_count,
            comment_count=comment_count,
            share_count=share_count,
            collect_count=collect_count,
            is_live_photo=is_live_photo,
            image_count=image_count,
            resolution=resolution,
            share_url=share_url,
            author_avatar_url=author_avatar,
            create_time=create_ts,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _safe_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _human_size(value: int) -> str:
        if value <= 0:
            return "未知"
        size = float(value)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024
        return f"{size:.1f} GB"

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
            "live": "直播",
            "live_replay": "直播回放",
        }.get(media_type, media_type or "未知")
