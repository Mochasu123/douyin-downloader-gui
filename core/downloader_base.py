import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple
from urllib.parse import urlparse

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core.api_client import DouyinAPIClient
from core.live_photo import merge_live_photo_files
from core.metadata import extract_author_sec_uid
from core.transcript_manager import TranscriptManager
from storage import Database, FileManager, MetadataHandler
from utils.logger import setup_logger
from utils.naming import (
    DEFAULT_FILE_TEMPLATE,
    DEFAULT_FOLDER_TEMPLATE,
    build_aweme_context,
    render_template,
)

logger = setup_logger("BaseDownloader")


class ProgressReporter(Protocol):
    def update_step(self, step: str, detail: str = "") -> None: ...

    def set_item_total(self, total: int, detail: str = "") -> None: ...

    def advance_item(self, status: str, detail: str = "") -> None: ...

    def on_file_progress(
        self, file_name: str, written: int, expected_size: Optional[int]
    ) -> None: ...

    def should_pause(self) -> bool: ...

    def should_cancel(self) -> bool: ...


class DownloadResult:
    def __init__(self):
        self.total = 0
        self.success = 0
        self.failed = 0
        self.skipped = 0

    def __str__(self):
        return f"Total: {self.total}, Success: {self.success}, Failed: {self.failed}, Skipped: {self.skipped}"


class BaseDownloader(ABC):
    def __init__(
        self,
        config: ConfigLoader,
        api_client: DouyinAPIClient,
        file_manager: FileManager,
        cookie_manager: CookieManager,
        database: Optional[Database] = None,
        rate_limiter: Optional[RateLimiter] = None,
        retry_handler: Optional[RetryHandler] = None,
        queue_manager: Optional[QueueManager] = None,
        progress_reporter: Optional[ProgressReporter] = None,
    ):
        self.config = config
        self.api_client = api_client
        self.file_manager = file_manager
        self.cookie_manager = cookie_manager
        self.database = database
        self.rate_limiter = rate_limiter or RateLimiter()
        self.retry_handler = retry_handler or RetryHandler()
        thread_count = int(self.config.get("thread", 5) or 5)
        self.queue_manager = queue_manager or QueueManager(max_workers=thread_count)
        self.progress_reporter = progress_reporter
        self.metadata_handler = MetadataHandler()
        self.transcript_manager = TranscriptManager(self.config, self.file_manager, self.database)
        self._local_aweme_ids: Optional[set[str]] = None
        self._aweme_id_pattern = re.compile(r"(?<!\d)(\d{15,20})(?!\d)")
        self._local_media_suffixes = {
            ".mp4",
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".mp3",
            ".m4a",
        }
        # 控制终端错误日志量，避免进度条被大量日志打断后出现重复重绘。
        self._download_error_log_count = 0
        self._download_error_log_limit = 5

    def _progress_update_step(self, step: str, detail: str = "") -> None:
        if not self.progress_reporter:
            return
        try:
            self.progress_reporter.update_step(step, detail)
        except Exception as exc:
            logger.debug("Progress update_step failed: %s", exc)

    def _progress_set_item_total(self, total: int, detail: str = "") -> None:
        if not self.progress_reporter:
            return
        try:
            self.progress_reporter.set_item_total(total, detail)
        except Exception as exc:
            logger.debug("Progress set_item_total failed: %s", exc)

    def _progress_advance_item(self, status: str, detail: str = "") -> None:
        if not self.progress_reporter:
            return
        try:
            self.progress_reporter.advance_item(status, detail)
        except Exception as exc:
            logger.debug("Progress advance_item failed: %s", exc)

    def _progress_file_progress(
        self, file_name: str, written: int, expected_size: Optional[int]
    ) -> None:
        if not self.progress_reporter:
            return
        try:
            fn = getattr(self.progress_reporter, "on_file_progress", None)
            if callable(fn):
                fn(file_name, written, expected_size)
        except Exception as exc:
            logger.debug("Progress on_file_progress failed: %s", exc)

    def _progress_should_pause(self) -> bool:
        if not self.progress_reporter:
            return False
        try:
            fn = getattr(self.progress_reporter, "should_pause", None)
            return bool(fn()) if callable(fn) else False
        except Exception as exc:
            logger.debug("Progress should_pause failed: %s", exc)
            return False

    def _progress_should_cancel(self) -> bool:
        if not self.progress_reporter:
            return False
        try:
            fn = getattr(self.progress_reporter, "should_cancel", None)
            return bool(fn()) if callable(fn) else False
        except Exception as exc:
            logger.debug("Progress should_cancel failed: %s", exc)
            return False

    def _progress_report_author(
        self,
        nickname: Optional[str] = None,
        sec_uid: Optional[str] = None,
    ) -> None:
        """Surface author metadata to the reporter so the hosting job can
        cache it for retry and display.

        Downloaders call this as soon as author info is known (user_info
        lookup for batch jobs, aweme_data.author for single-video jobs).
        Safe to call with `None` values — the reporter drops empty payloads.
        """
        if not self.progress_reporter:
            return
        try:
            fn = getattr(self.progress_reporter, "on_author", None)
            if callable(fn):
                fn(nickname=nickname, sec_uid=sec_uid)
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("Progress on_author failed: %s", exc)

    def _log_download_error(self, log_fn, message: str) -> None:
        if self._download_error_log_count < self._download_error_log_limit:
            log_fn(message)
        elif self._download_error_log_count == self._download_error_log_limit:
            logger.error("Too many download errors, suppressing further per-file logs...")
        self._download_error_log_count += 1

    def _download_headers(self, user_agent: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "Referer": f"{self.api_client.BASE_URL}/",
            "Origin": self.api_client.BASE_URL,
            "Accept": "*/*",
        }

        headers["User-Agent"] = user_agent or self.api_client.headers.get("User-Agent", "")
        return headers

    @abstractmethod
    async def download(self, parsed_url: Dict[str, Any]) -> DownloadResult:
        pass

    async def _should_download(self, aweme_id: str) -> bool:
        in_local = self._is_locally_downloaded(aweme_id)
        in_db = False
        if self.database:
            in_db = await self.database.is_downloaded(aweme_id)

        if in_db and in_local:
            return False

        if in_db and not in_local:
            logger.info(
                "Aweme %s exists in database but media file not found locally, retry download",
                aweme_id,
            )
            return True

        if in_local:
            logger.info("Aweme %s already exists locally, skipping", aweme_id)
            return False

        return True

    def _is_locally_downloaded(self, aweme_id: str) -> bool:
        if not aweme_id:
            return False

        if self._local_aweme_ids is None:
            self._build_local_aweme_index()

        if self._local_aweme_ids is None:
            return False
        return aweme_id in self._local_aweme_ids

    def _build_local_aweme_index(self):
        base_path = self.file_manager.base_path
        aweme_ids: set[str] = set()

        if base_path.exists():
            for path in base_path.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in self._local_media_suffixes:
                    continue
                try:
                    if path.stat().st_size <= 0:
                        continue
                except OSError:
                    continue
                for match in self._aweme_id_pattern.finditer(path.name):
                    aweme_ids.add(match.group(1))

        self._local_aweme_ids = aweme_ids

    def _mark_local_aweme_downloaded(self, aweme_id: str):
        if not aweme_id:
            return

        if self._local_aweme_ids is None:
            self._local_aweme_ids = set()
        self._local_aweme_ids.add(aweme_id)

    def _filter_by_time(self, aweme_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        start_time = self.config.get("start_time")
        end_time = self.config.get("end_time")

        if not start_time and not end_time:
            return aweme_list

        start_ts = (
            int(datetime.strptime(start_time, "%Y-%m-%d").timestamp()) if start_time else None
        )
        end_ts = int(datetime.strptime(end_time, "%Y-%m-%d").timestamp()) if end_time else None

        filtered: List[Dict[str, Any]] = []
        for aweme in aweme_list:
            create_time = aweme.get("create_time", 0)
            if start_ts is not None and create_time < start_ts:
                continue
            if end_ts is not None and create_time > end_ts:
                continue
            filtered.append(aweme)

        return filtered

    def _limit_count(self, aweme_list: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
        number_config = self.config.get("number", {})
        limit = number_config.get(mode, 0)

        if limit > 0:
            return aweme_list[:limit]
        return aweme_list

    async def _download_aweme_assets(
        self,
        aweme_data: Dict[str, Any],
        author_name: str,
        mode: Optional[str] = None,
        *,
        db_batch: Optional[List[Dict[str, Any]]] = None,
        collection_dir: Optional[str] = None,
    ) -> bool:
        aweme_id = aweme_data.get("aweme_id")
        if not aweme_id:
            logger.error("Missing aweme_id in aweme data")
            return False

        desc = (aweme_data.get("desc", "no_title") or "").strip() or "no_title"
        publish_ts, publish_date = self._resolve_publish_time(aweme_data.get("create_time"))
        if not publish_date:
            publish_date = datetime.now().strftime("%Y-%m-%d")
            logger.warning(
                "Aweme %s missing/invalid create_time, fallback to current date %s",
                aweme_id,
                publish_date,
            )
        media_type = self._detect_media_type(aweme_data)
        template_context = build_aweme_context(
            aweme_id=str(aweme_id),
            title=desc,
            author_name=author_name,
            author_sec_uid=extract_author_sec_uid(aweme_data),
            publish_date=publish_date,
            publish_ts=publish_ts,
            media_type=media_type,
            mode=mode,
        )
        filename_template = self.config.get("filename_template") or DEFAULT_FILE_TEMPLATE
        folder_template = self.config.get("folder_template") or DEFAULT_FOLDER_TEMPLATE
        file_stem = render_template(
            filename_template,
            template_context,
            fallback=f"{publish_date}_{aweme_id}",
        )
        folder_name = render_template(
            folder_template,
            template_context,
            fallback=f"{publish_date}_{aweme_id}",
        )

        save_dir = self.file_manager.get_save_path(
            author_name=author_name,
            mode=mode,
            aweme_title=desc,
            aweme_id=aweme_id,
            folderstyle=self.config.get("folderstyle", True),
            download_date=publish_date,
            folder_name=folder_name,
            author_sec_uid=extract_author_sec_uid(aweme_data),
            author_dir_style=self.config.get("author_dir") or "nickname",
            group_by_mode=self.config.get("group_by_mode", True),
            collection_dir=collection_dir,
        )
        downloaded_files: List[Path] = []

        session = await self.api_client.get_session()
        video_path: Optional[Path] = None

        if media_type == "video":
            video_candidates = self._build_video_url_candidates(aweme_data)
            if not video_candidates:
                logger.error("No playable video URL found for aweme %s", aweme_id)
                return False

            video_path = save_dir / f"{file_stem}.mp4"
            if not await self._download_video_with_fallback(video_candidates, video_path, session):
                return False
            downloaded_files.append(video_path)

            if self.config.get("cover"):
                cover_source = aweme_data.get("video", {}).get("cover")
                if self._extract_urls(cover_source):
                    cover_path = save_dir / f"{file_stem}_cover.jpg"
                    if await self._download_first_available(
                        cover_source,
                        cover_path,
                        session,
                        headers=self._download_headers(),
                        optional=True,
                    ):
                        downloaded_files.append(cover_path)

            if self.config.get("music"):
                music_url = self._extract_first_url(aweme_data.get("music", {}).get("play_url"))
                if music_url:
                    music_path = save_dir / f"{file_stem}_music.mp3"
                    if await self._download_with_retry(
                        music_url,
                        music_path,
                        session,
                        headers=self._download_headers(),
                        optional=True,
                    ):
                        downloaded_files.append(music_path)

        elif media_type == "gallery":
            gallery_assets = self._collect_gallery_assets(aweme_data)
            image_url_candidates = [
                candidates for _, candidates, _ in gallery_assets if candidates
            ]
            image_live_pairs = [
                (gallery_index, live_url)
                for gallery_index, _, live_url in gallery_assets
                if live_url
            ]
            logger.info(
                "Gallery aweme %s: %d image(s), %d live photo(s)",
                aweme_id,
                len(image_url_candidates),
                len(image_live_pairs),
            )
            if not image_url_candidates and not image_live_pairs:
                logger.error(
                    "No gallery assets found for aweme %s (aweme_type=%s, "
                    "has image_post_info=%s, has images=%s)",
                    aweme_id,
                    aweme_data.get("aweme_type"),
                    "image_post_info" in aweme_data,
                    "images" in aweme_data,
                )
                return False

            downloaded_image_paths: List[Path] = []
            for index, candidates in enumerate(image_url_candidates, start=1):
                download_result: bool | Path = False
                # 与 _download_first_available 同原则：多镜像时镜像列表本身
                # 就是重试机制（每镜像单次尝试），单镜像才保留退避重试——
                # 否则死镜像 × 每镜像 4 次退避嵌套，一张图最坏能拖数分钟。
                use_backoff = len(candidates) == 1
                for url_index, image_url in enumerate(candidates):
                    is_last = url_index == len(candidates) - 1
                    suffix = self._infer_image_extension(image_url)
                    image_path = save_dir / f"{file_stem}_{index}{suffix}"
                    download_result = await self._download_with_retry(
                        image_url,
                        image_path,
                        session,
                        headers=self._download_headers(),
                        prefer_response_content_type=True,
                        return_saved_path=True,
                        optional=not is_last,
                        retry=use_backoff,
                    )
                    if download_result:
                        saved_image_path = (
                            download_result if isinstance(download_result, Path) else image_path
                        )
                        downloaded_files.append(saved_image_path)
                        downloaded_image_paths.append(saved_image_path)
                        break
                if not download_result:
                    logger.error(f"Failed downloading image {index} for aweme {aweme_id}")
                    return False

            downloaded_live_paths: List[Path] = []
            for index, (_gallery_index, live_url) in enumerate(
                image_live_pairs, start=1
            ):
                suffix = Path(urlparse(live_url).path).suffix or ".mp4"
                live_path = save_dir / f"{file_stem}_live_{index}{suffix}"
                success = await self._download_with_retry(
                    live_url,
                    live_path,
                    session,
                    headers=self._download_headers(),
                )
                if not success:
                    logger.error(f"Failed downloading live image {index} for aweme {aweme_id}")
                    return False
                downloaded_files.append(live_path)
                downloaded_live_paths.append(live_path)

            # 动图合并：静态图 + 动图视频 → 华为手机可直接查看的动态照片
            if self.config.get("live_photo_merge", True):
                image_pos_by_gallery: Dict[int, int] = {}
                for position, (gallery_index, candidates, _live_url) in enumerate(
                    gallery_assets, start=1
                ):
                    if candidates:
                        image_pos_by_gallery[gallery_index] = position
                for index, (gallery_index, _live_url) in enumerate(
                    image_live_pairs, start=1
                ):
                    image_position = image_pos_by_gallery.get(gallery_index)
                    if image_position is None or image_position > len(
                        downloaded_image_paths
                    ):
                        continue
                    still_path = downloaded_image_paths[image_position - 1]
                    video_path = downloaded_live_paths[index - 1]
                    merged_path = save_dir / f"{file_stem}_live_{index}.jpg"
                    if merge_live_photo_files(still_path, video_path, merged_path):
                        downloaded_files.append(merged_path)
        else:
            logger.error("Unsupported media type for aweme %s: %s", aweme_id, media_type)
            return False

        if self.config.get("avatar"):
            avatar_source = aweme_data.get("author", {}).get("avatar_larger")
            if self._extract_urls(avatar_source):
                avatar_path = save_dir / f"{file_stem}_avatar.jpg"
                if await self._download_first_available(
                    avatar_source,
                    avatar_path,
                    session,
                    headers=self._download_headers(),
                    optional=True,
                ):
                    downloaded_files.append(avatar_path)

        if self.config.get("json"):
            json_path = save_dir / f"{file_stem}_data.json"
            if await self.metadata_handler.save_metadata(aweme_data, json_path):
                downloaded_files.append(json_path)

        comments_cfg = self.config.get("comments") or {}
        if isinstance(comments_cfg, dict) and comments_cfg.get("enabled"):
            from core.comments_collector import CommentsCollector

            collector = CommentsCollector(
                self.api_client,
                self.metadata_handler,
                include_replies=bool(comments_cfg.get("include_replies", False)),
                max_comments=int(comments_cfg.get("max_comments", 0) or 0),
                page_size=int(comments_cfg.get("page_size", 20) or 20),
            )
            comments_path = save_dir / f"{file_stem}_comments.json"
            saved = await collector.collect_and_save(aweme_id, comments_path)
            if saved is not None:
                downloaded_files.append(comments_path)

        author = aweme_data.get("author", {})
        if self.database:
            metadata_json = json.dumps(aweme_data, ensure_ascii=False)
            record = {
                "aweme_id": aweme_id,
                "aweme_type": media_type,
                "title": desc,
                "author_id": author.get("uid"),
                "author_name": author.get("nickname", author_name),
                "create_time": aweme_data.get("create_time"),
                "file_path": str(save_dir),
                "metadata": metadata_json,
                # Attach sec_uid onto the payload so both the batched path
                # (add_aweme_batch iterates `record["author_sec_uid"]`) and
                # the single-write path (add_aweme reads the payload as
                # fallback when the kwarg is None) pick it up identically.
                "author_sec_uid": extract_author_sec_uid(aweme_data),
            }
            # Caller may opt into batched DB writes by passing a list; we just
            # accumulate the record and let the caller commit them all at once.
            if db_batch is not None:
                db_batch.append(record)
            else:
                await self.database.add_aweme(record)

        manifest_record = {
            "date": publish_date,
            "aweme_id": aweme_id,
            "author_name": author.get("nickname", author_name),
            "desc": desc,
            "media_type": media_type,
            "tags": self._extract_tags(aweme_data),
            "file_names": [path.name for path in downloaded_files],
            "file_paths": [self._to_manifest_path(path) for path in downloaded_files],
        }
        if publish_ts:
            manifest_record["publish_timestamp"] = publish_ts
        await self.metadata_handler.append_download_manifest(
            self.file_manager.base_path, manifest_record
        )

        if media_type == "video" and video_path is not None:
            transcript_result = await self.transcript_manager.process_video(
                video_path, aweme_id=aweme_id
            )
            transcript_status = transcript_result.get("status")
            if transcript_status == "skipped":
                logger.info(
                    "Transcript skipped for aweme %s: %s",
                    aweme_id,
                    transcript_result.get("reason", "unknown"),
                )
            elif transcript_status == "failed":
                logger.warning(
                    "Transcript failed for aweme %s: %s",
                    aweme_id,
                    transcript_result.get("error", "unknown"),
                )

        self._mark_local_aweme_downloaded(aweme_id)
        logger.info("Downloaded %s: %s (%s)", media_type, desc, aweme_id)
        return True

    async def _download_with_retry(
        self,
        url: str,
        save_path: Path,
        session,
        *,
        headers: Optional[Dict[str, str]] = None,
        optional: bool = False,
        prefer_response_content_type: bool = False,
        return_saved_path: bool = False,
        retry: bool = True,
    ) -> bool | Path:
        async def _task():
            download_result = await self.file_manager.download_file(
                url,
                save_path,
                session,
                headers=headers,
                proxy=getattr(self.api_client, "proxy", None),
                prefer_response_content_type=prefer_response_content_type,
                return_saved_path=return_saved_path,
                progress_callback=lambda written, total: self._progress_file_progress(
                    save_path.name, written, total
                ),
                should_pause=self._progress_should_pause,
                should_cancel=self._progress_should_cancel,
            )
            if not download_result:
                raise RuntimeError(f"Download failed for {url}")
            return download_result

        try:
            if retry:
                return await self.retry_handler.execute_with_retry(_task)
            return await _task()
        except Exception as error:
            log_fn = logger.warning if optional else logger.error
            self._log_download_error(
                log_fn,
                f"Download error for {save_path.name}: {error}",
            )
            return False

    async def _download_video_with_fallback(
        self,
        candidates: List[Tuple[str, Dict[str, str]]],
        save_path: Path,
        session,
    ) -> bool:
        """在候选地址间降级下载视频：每轮按序各尝试一次，整轮失败再退避重试。

        play 端点的失败多为 302 落点抽签不走运（PCDN 死节点），重试同一
        URL 有意义；直连地址失败（403/过期）则应换下一候选。按轮扫 +
        RetryHandler 退避兼顾两种失败模式，单候选时行为与旧退避重试一致。
        """
        if not candidates:
            return False

        async def _attempt_round() -> bool:
            for url, headers in candidates:
                if await self._download_with_retry(
                    url,
                    save_path,
                    session,
                    headers=headers,
                    optional=True,
                    retry=False,
                ):
                    return True
            raise RuntimeError(
                f"All {len(candidates)} video url candidate(s) failed for {save_path.name}"
            )

        try:
            return await self.retry_handler.execute_with_retry(_attempt_round)
        except Exception:
            return False

    async def _download_first_available(
        self,
        source: Any,
        save_path: Path,
        session,
        *,
        headers: Optional[Dict[str, str]] = None,
        optional: bool = False,
        **kwargs,
    ) -> bool | Path:
        """Download an asset, falling back across every mirror in ``url_list``.

        Douyin serves images from multiple CDN mirrors (e.g. p3/p9). The first
        mirror occasionally returns 403 while a later one succeeds, so try each
        URL in turn and return on the first success instead of giving up after
        ``url_list[0]`` and silently dropping the asset.

        存在多个镜像时，镜像列表本身就是重试机制：每个镜像只尝试一次，
        避免在已知会持续 403 的死镜像上叠加多轮退避重试（单个封面最多
        可拖慢 20+ 秒并占用下载并发槽）。仅单一 URL 时保留退避重试。
        """
        urls = self._extract_urls(source)
        use_backoff = len(urls) == 1
        result: bool | Path = False
        for index, url in enumerate(urls):
            is_last = index == len(urls) - 1
            result = await self._download_with_retry(
                url,
                save_path,
                session,
                headers=headers,
                # Keep earlier-mirror failures quiet; only the final attempt
                # reflects the caller's chosen log level.
                optional=optional or not is_last,
                retry=use_backoff,
                **kwargs,
            )
            if result:
                return result
        return result

    # aweme_type codes that indicate image/note content
    _GALLERY_AWEME_TYPES = {2, 68, 150}
    _PLAY_ADDR_KEYS = (
        "play_addr_h264",
        "play_addr_265",
        "play_addr_256",
        "play_addr",
    )

    def _detect_media_type(self, aweme_data: Dict[str, Any]) -> str:
        if self._iter_gallery_items(aweme_data):
            return "gallery"
        aweme_type = aweme_data.get("aweme_type")
        if isinstance(aweme_type, int) and aweme_type in self._GALLERY_AWEME_TYPES:
            video = aweme_data.get("video") if isinstance(aweme_data.get("video"), dict) else {}
            if self._has_video_source(video):
                logger.info(
                    "Detected note video via aweme_type=%s for aweme %s",
                    aweme_type,
                    aweme_data.get("aweme_id"),
                )
                return "video"
            logger.info(
                "Detected gallery via aweme_type=%s for aweme %s",
                aweme_type,
                aweme_data.get("aweme_id"),
            )
            return "gallery"
        return "video"

    def _build_no_watermark_url(
        self, aweme_data: Dict[str, Any]
    ) -> Optional[Tuple[str, Dict[str, str]]]:
        """Best single video URL (kept for existing callers/tests);
        see :meth:`_build_video_url_candidates` for the preference order."""
        candidates = self._build_video_url_candidates(aweme_data)
        return candidates[0] if candidates else None

    def _build_video_url_candidates(
        self, aweme_data: Dict[str, Any]
    ) -> List[Tuple[str, Dict[str, str]]]:
        """按优先级返回可依次尝试的视频下载地址（url + 请求头）。

        直连 CDN（douyinvod.com 等）优先于 ``/aweme/v1/play/`` 签名端点：
        play 端点 302 后可能落到打不通的 PCDN 节点（``*.qtaeixd.com`` 高位
        端口），直连域名走标准 CDN（commit 099aae5 声明的意图，此前被循环
        内对 douyin.com 候选的提前 return 打破）。play 端点保留为降级候选，
        供直连失败时兜底。没有净版候选时按旧逻辑回退：uri 构造签名地址 →
        带水印地址。
        """
        video = aweme_data.get("video", {})
        quality = str(self.config.get("video_quality") or "highest")
        play_addr = self._pick_preferred_play_addr(video, quality) or {}
        url_candidates = [c for c in (play_addr.get("url_list") or []) if c]
        url_candidates.sort(key=lambda u: 0 if "watermark=0" in u else 1)

        direct_candidates, play_candidate, watermarked_candidate = self._partition_video_candidates(
            url_candidates
        )

        candidates: List[Tuple[str, Dict[str, str]]] = list(direct_candidates)
        if play_candidate:
            candidates.append(self._sign_play_candidate(play_candidate))
        if candidates:
            return candidates

        constructed = self._build_signed_play_url(video, play_addr, quality)
        if constructed:
            return [constructed]
        if watermarked_candidate:
            return [watermarked_candidate]
        return []

    def _partition_video_candidates(
        self, url_candidates: List[str]
    ) -> Tuple[
        List[Tuple[str, Dict[str, str]]],
        Optional[str],
        Optional[Tuple[str, Dict[str, str]]],
    ]:
        """把 url_list 分拣为（全部净版直连镜像, 首个净版 play 端点, 首个带水印）。

        直连镜像常有 2-3 个不同主机（v3/v9 等），全部保留并维持 url_list
        原序——只取第一个会在镜像 1 挂掉时跳过健康的镜像 2、直接进 play
        端点的 PCDN 抽签。play 端点多条等价（同一端点），取首个即可，签名
        推迟到真正选用时（:meth:`_sign_play_candidate`）；带水印取首个作
        最后兜底。
        """
        direct: List[Tuple[str, Dict[str, str]]] = []
        play: Optional[str] = None
        watermarked: Optional[Tuple[str, Dict[str, str]]] = None

        for candidate in url_candidates:
            is_watermarked = self._is_watermarked_media_url(candidate)

            if urlparse(candidate).netloc.endswith("douyin.com"):
                if is_watermarked:
                    if watermarked is None:
                        watermarked = self._sign_play_candidate(candidate)
                    continue
                play = play or candidate
                continue

            if is_watermarked:
                watermarked = watermarked or (candidate, self._download_headers())
            else:
                direct.append((candidate, self._download_headers()))

        return direct, play, watermarked

    def _sign_play_candidate(self, candidate: str) -> Tuple[str, Dict[str, str]]:
        """Sign a douyin.com play URL when it lacks X-Bogus; pass through otherwise."""
        if "X-Bogus=" not in candidate:
            signed_url, ua = self.api_client.sign_url(candidate)
            return signed_url, self._download_headers(user_agent=ua)
        return candidate, self._download_headers()

    def _build_signed_play_url(
        self,
        video: Dict[str, Any],
        play_addr: Dict[str, Any],
        quality: str,
    ) -> Optional[Tuple[str, Dict[str, str]]]:
        uri = play_addr.get("uri") or video.get("vid") or video.get("download_addr", {}).get("uri")
        if not uri:
            return None
        # Douyin /aweme/v1/play/ accepts a limited set of ratio strings.
        # Preserve the selected track's actual tier when its direct URLs
        # cannot be used; otherwise fall back to the configured preference.
        selected_entry = self._find_bit_rate_entry(video, play_addr)
        short_edge, _ = self._resolution_metrics(selected_entry, play_addr)
        selected_ratio = f"{short_edge}p"
        normalised_quality = quality.strip().lower()
        ratio_map = {
            "highest": "1080p",
            "lowest": "540p",
        }
        fallback_ratio = ratio_map.get(
            normalised_quality,
            normalised_quality if normalised_quality in self._QUALITY_TARGET_WIDTH else "1080p",
        )
        ratio = selected_ratio if selected_ratio in self._QUALITY_TARGET_WIDTH else fallback_ratio
        params = {
            "video_id": uri,
            "ratio": ratio,
            "line": "0",
            "is_play_url": "1",
            "watermark": "0",
            "source": "PackSourceEnum_PUBLISH",
        }
        signed_url, ua = self.api_client.build_signed_path("/aweme/v1/play/", params)
        return signed_url, self._download_headers(user_agent=ua)

    # 视频画质选择支持的规格名称。值保留为横屏长边尺寸，用于兼容只有
    # width 的旧响应；完整 width/height 响应会按短边匹配 1080p/720p 等档位。
    _QUALITY_TARGET_WIDTH: Dict[str, int] = {
        "1440p": 2560,
        "1080p": 1920,
        "720p": 1280,
        "540p": 960,
        "480p": 854,
        "360p": 640,
    }

    @staticmethod
    def _find_bit_rate_entry(video: Dict[str, Any], play_addr: Dict[str, Any]) -> Dict[str, Any]:
        entries = video.get("bit_rate") if isinstance(video, dict) else None
        if not isinstance(entries, list):
            return {}
        for entry in entries:
            if isinstance(entry, dict) and entry.get("play_addr") is play_addr:
                return entry
        return {}

    @staticmethod
    def _resolution_metrics(entry: Dict[str, Any], play_addr: Dict[str, Any]) -> Tuple[int, int]:
        """Return ``(short_edge, pixels)`` for portrait and landscape tracks."""
        try:
            width = int(play_addr.get("width") or entry.get("width") or 0)
            height = int(play_addr.get("height") or entry.get("height") or 0)
        except (TypeError, ValueError):
            return 0, 0
        if width > 0 and height > 0:
            return min(width, height), width * height
        long_edge = max(width, height)
        if long_edge <= 0:
            return 0, 0
        nearest = min(
            BaseDownloader._QUALITY_TARGET_WIDTH.items(),
            key=lambda item: abs(item[1] - long_edge),
        )[0]
        short_edge = int(nearest[:-1])
        return short_edge, long_edge * short_edge

    @staticmethod
    def _pick_highest_quality_play_addr(video: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Shortcut for highest-quality selection (backward-compatible).

        Kept for older callers; new code should use
        :meth:`_pick_play_addr_by_quality` with an explicit quality string.
        """
        return BaseDownloader._pick_play_addr_by_quality(video, "highest")

    @staticmethod
    def _pick_play_addr_by_quality(
        video: Dict[str, Any], quality: str = "highest"
    ) -> Optional[Dict[str, Any]]:
        """从 video.bit_rate 多档率中按目标画质挑选 play_addr。

        抖音 API 的 ``video.bit_rate`` 是按质量排序的字典列表，每项含
        ``bit_rate``（码率）与 ``play_addr``（内含 URL、width 与 height）。

        - ``highest`` / 未知值 / 空：取分辨率最高的档；同分辨率按 bit_rate 决胜。
        - ``lowest``：取 bit_rate 最小的档；同码率按 width 小者优先。
        - ``<N>p``（如 ``1080p``）：按画面短边最接近目标值的档；完全没有 bit_rate
          数据时返回 ``None``，让调用方回退到 ``video.play_addr``。
        """
        bit_rates = video.get("bit_rate") if isinstance(video, dict) else None
        if not isinstance(bit_rates, list) or not bit_rates:
            return None

        entries: List[Tuple[int, int, int, Dict[str, Any]]] = []
        for entry in bit_rates:
            if not isinstance(entry, dict):
                continue
            play_addr = entry.get("play_addr")
            if not isinstance(play_addr, dict):
                continue
            try:
                br = int(entry.get("bit_rate") or 0)
            except (TypeError, ValueError):
                br = 0
            short_edge, pixels = BaseDownloader._resolution_metrics(entry, play_addr)
            entries.append((br, short_edge, pixels, play_addr))
        if not entries:
            return None

        normalised = (quality or "highest").strip().lower()

        if normalised == "lowest":
            entries.sort(key=lambda t: (t[0], t[2]))
            return entries[0][3]

        if normalised in BaseDownloader._QUALITY_TARGET_WIDTH:
            target_edge = int(normalised[:-1])
            # Closest short edge to target; tie-break by higher bit_rate so we
            # don't accidentally pick a re-encoded low-bitrate copy.
            entries.sort(key=lambda t: (abs(t[1] - target_edge), -t[0], -t[2]))
            return entries[0][3]

        # Default / "highest": highest resolution, tie-break by bit rate.
        entries.sort(key=lambda t: (-t[2], -t[0], -t[1]))
        return entries[0][3]

    def _collect_image_urls(self, aweme_data: Dict[str, Any]) -> List[str]:
        return [
            candidates[0]
            for candidates in self._collect_image_url_candidates(aweme_data)
            if candidates
        ]

    def _collect_image_url_candidates(self, aweme_data: Dict[str, Any]) -> List[List[str]]:
        return [
            candidates
            for _gallery_index, candidates, _live_url in self._collect_gallery_assets(
                aweme_data
            )
            if candidates
        ]

    def _collect_gallery_assets(
        self, aweme_data: Dict[str, Any]
    ) -> List[Tuple[int, List[str], Optional[str]]]:
        """收集图文每一项的图片候选与动图视频地址。

        Returns:
            [(gallery_index, image_url_candidates, live_video_url)]，与
            ``_iter_gallery_items`` 的下标一致；既无图片也无动图的项跳过。
        """
        gallery_items = self._iter_gallery_items(aweme_data)
        quality = str(self.config.get("video_quality") or "highest")
        assets: List[Tuple[int, List[str], Optional[str]]] = []
        for gallery_index, item in enumerate(gallery_items):
            if not isinstance(item, dict):
                continue
            candidates = self._collect_ranked_media_urls(
                (item.get("watermark_free_download_url_list"), item, 0),
                (item.get("origin_image"), item.get("origin_image"), 1),
                (item.get("display_image"), item.get("display_image"), 2),
                (item, item, 3),
                (item.get("download_url"), item.get("download_url"), 4),
                (item.get("download_addr"), item.get("download_addr"), 5),
                (item.get("download_url_list"), item, 6),
                (item.get("owner_watermark_image"), item.get("owner_watermark_image"), 7),
            )
            video = item.get("video") if isinstance(item.get("video"), dict) else {}
            preferred_play_addr = self._pick_preferred_play_addr(video, quality)
            live_url = self._pick_first_media_url(
                preferred_play_addr,
                video.get("play_addr_h264"),
                video.get("play_addr_265"),
                video.get("play_addr_256"),
                video.get("play_addr"),
                video.get("download_addr"),
                item.get("video_play_addr"),
                item.get("video_download_addr"),
            )
            if candidates or live_url:
                assets.append((gallery_index, candidates, live_url))
        if not assets:
            logger.warning(
                "No gallery assets extracted for aweme %s; gallery items count=%d",
                aweme_data.get("aweme_id"),
                len(gallery_items),
            )
        return assets

    def _collect_image_live_pairs(
        self, aweme_data: Dict[str, Any]
    ) -> List[Tuple[int, str]]:
        """返回 [(gallery_index, live_video_url)]，用于静态图与动图视频配对。"""
        return [
            (gallery_index, live_url)
            for gallery_index, _candidates, live_url in self._collect_gallery_assets(
                aweme_data
            )
            if live_url
        ]

    @staticmethod
    def _pick_preferred_play_addr(
        video: Dict[str, Any], quality: str = "highest"
    ) -> Optional[Dict[str, Any]]:
        preferred = BaseDownloader._pick_play_addr_by_quality(video, quality)
        if preferred:
            return preferred
        if not isinstance(video, dict):
            return None
        primary = video.get("play_addr")
        if isinstance(primary, dict) and primary.get("uri"):
            return primary
        for key in BaseDownloader._PLAY_ADDR_KEYS:
            candidate = video.get(key)
            if isinstance(candidate, dict) and (
                BaseDownloader._extract_first_url(candidate) or candidate.get("uri")
            ):
                return candidate
        return None

    @staticmethod
    def _has_video_source(video: Dict[str, Any]) -> bool:
        if BaseDownloader._pick_preferred_play_addr(video):
            return True
        if not isinstance(video, dict):
            return False
        return bool(
            video.get("vid")
            or (isinstance(video.get("download_addr"), dict) and video["download_addr"].get("uri"))
        )

    def _collect_image_live_urls(self, aweme_data: Dict[str, Any]) -> List[str]:
        live_urls: List[str] = []
        quality = str(self.config.get("video_quality") or "highest")
        for item in self._iter_gallery_items(aweme_data):
            if not isinstance(item, dict):
                continue
            video = item.get("video") if isinstance(item.get("video"), dict) else {}
            # 实况图同样会有 bit_rate 多档，按配置的画质偏好选择对应档位。
            preferred_play_addr = self._pick_preferred_play_addr(video, quality)
            live_url = self._pick_first_media_url(
                preferred_play_addr,
                video.get("play_addr_h264"),
                video.get("play_addr_265"),
                video.get("play_addr_256"),
                video.get("play_addr"),
                video.get("download_addr"),
                item.get("video_play_addr"),
                item.get("video_download_addr"),
            )
            if live_url:
                live_urls.append(live_url)
        return self._deduplicate_urls(live_urls)

    @staticmethod
    def _iter_gallery_items(aweme_data: Dict[str, Any]) -> List[Any]:
        image_post = aweme_data.get("image_post_info")
        if isinstance(image_post, dict):
            for key in ("images", "image_list"):
                candidate = image_post.get(key)
                if isinstance(candidate, list) and candidate:
                    return candidate
        images = aweme_data.get("images") or aweme_data.get("image_list") or []
        if isinstance(images, list):
            return images
        return []

    @staticmethod
    def _deduplicate_urls(urls: List[str]) -> List[str]:
        deduped: List[str] = []
        seen: set[str] = set()
        for url in urls:
            if not url or url in seen:
                continue
            seen.add(url)
            deduped.append(url)
        return deduped

    @staticmethod
    def _pick_first_media_url(*sources: Any) -> Optional[str]:
        for source in sources:
            candidate = BaseDownloader._extract_first_url(source)
            if candidate:
                return candidate
        return None

    @staticmethod
    def _collect_ranked_media_urls(*sources: Tuple[Any, Any, int]) -> List[str]:
        entries: List[Tuple[Tuple[int, int, int, int], str]] = []
        for source, metadata, source_rank in sources:
            for candidate in BaseDownloader._extract_urls(source):
                entries.append(
                    (
                        BaseDownloader._gallery_image_sort_key(candidate, metadata, source_rank),
                        candidate,
                    )
                )

        urls: List[str] = []
        seen: set[str] = set()
        for _key, candidate in sorted(entries, key=lambda entry: entry[0]):
            if candidate in seen:
                continue
            seen.add(candidate)
            urls.append(candidate)
        return urls

    @staticmethod
    def _gallery_image_sort_key(
        url: str, metadata: Any, source_rank: int
    ) -> Tuple[int, int, int, int]:
        watermark_rank = (
            1 if source_rank >= 4 or BaseDownloader._is_watermarked_media_url(url) else 0
        )
        pixels = BaseDownloader._image_resolution_score(metadata)
        return (watermark_rank, -pixels, source_rank, BaseDownloader._image_format_rank(url))

    @staticmethod
    def _image_resolution_score(source: Any) -> int:
        if not isinstance(source, dict):
            return 0

        width = BaseDownloader._positive_int(source.get("width") or source.get("w"))
        height = BaseDownloader._positive_int(source.get("height") or source.get("h"))
        if width and height:
            return width * height
        # Some response variants expose only one side; use it as a weak hint
        # after exact pixel-area ranking, then fall back to source preference.
        return width or height or 0

    @staticmethod
    def _positive_int(value: Any) -> int:
        try:
            number = int(float(str(value).strip()))
        except (TypeError, ValueError):
            return 0
        return number if number > 0 else 0

    @staticmethod
    def _image_format_rank(url: str) -> int:
        path = (urlparse(url).path or "").lower()
        return 1 if ".webp" in path else 0

    @staticmethod
    def _is_watermarked_media_url(url: str) -> bool:
        normalized = url.lower()
        watermark_hints = (
            "tplv-dy-water",
            "dy-water",
            "owner_watermark",
            "watermark_image",
            "watermark=1",
            "playwm",
        )
        return any(hint in normalized for hint in watermark_hints)

    @staticmethod
    def _extract_first_url(source: Any) -> Optional[str]:
        urls = BaseDownloader._extract_urls(source)
        return urls[0] if urls else None

    @staticmethod
    def _extract_urls(source: Any) -> List[str]:
        if isinstance(source, dict):
            url_list = source.get("url_list") or source.get("urlList")
            if isinstance(url_list, list) and url_list:
                return [item for item in url_list if isinstance(item, str) and item]
        elif isinstance(source, list) and source:
            return [item for item in source if isinstance(item, str) and item]
        elif isinstance(source, str) and source:
            return [source]
        return []

    @staticmethod
    def _infer_image_extension(image_url: str) -> str:
        allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        if not image_url:
            return ".jpg"

        image_path = (urlparse(image_url).path or "").lower()
        raw_suffix = Path(image_path).suffix.lower()
        if raw_suffix in allowed_exts:
            return raw_suffix

        matches = re.findall(r"\.(?:jpe?g|png|webp|gif)(?=[^a-z0-9]|$)", image_path)
        if matches:
            return matches[-1].lower()

        return ".jpg"

    @staticmethod
    def _resolve_publish_time(create_time: Any) -> Tuple[Optional[int], str]:
        if create_time in (None, ""):
            return None, ""

        try:
            publish_ts = int(create_time)
            if publish_ts <= 0:
                return None, ""
            return publish_ts, datetime.fromtimestamp(publish_ts).strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError, OverflowError):
            return None, ""

    @staticmethod
    def _extract_tags(aweme_data: Dict[str, Any]) -> List[str]:
        tags: List[str] = []

        def _append_tag(raw_tag: Any):
            if not raw_tag:
                return
            normalized_tag = str(raw_tag).strip().lstrip("#")
            if normalized_tag and normalized_tag not in tags:
                tags.append(normalized_tag)

        for item in aweme_data.get("text_extra") or []:
            if not isinstance(item, dict):
                continue
            _append_tag(item.get("hashtag_name"))
            _append_tag(item.get("tag_name"))

        for item in aweme_data.get("cha_list") or []:
            if not isinstance(item, dict):
                continue
            _append_tag(item.get("cha_name"))
            _append_tag(item.get("name"))

        desc = aweme_data.get("desc") or ""
        for hashtag in re.findall(r"#([^\s#]+)", desc):
            _append_tag(hashtag)

        return tags

    def _to_manifest_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.file_manager.base_path))
        except ValueError:
            return str(path)
