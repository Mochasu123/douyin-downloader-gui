"""Controller – business logic bridge between GUI widgets and backend.

Handles config loading / saving, preview triggering, download orchestration,
thread management, and output queue draining.
"""

from __future__ import annotations

import asyncio
import io
import json
import queue
import threading
from copy import deepcopy
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable, Dict, List, Optional

import yaml

from core import LoginRequiredError

# ── video_quality 配置值 ↔ 界面中文标签 ─────────────────────────────
_VIDEO_QUALITY_LABELS = ("最高", "1440p", "1080p", "720p", "540p", "480p", "360p", "最低")
_VIDEO_QUALITY_VALUE_TO_LABEL = {"highest": "最高", "lowest": "最低"}
for _q in ("1440p", "1080p", "720p", "540p", "480p", "360p"):
    _VIDEO_QUALITY_VALUE_TO_LABEL[_q] = _q
_VIDEO_QUALITY_LABEL_TO_VALUE = {v: k for k, v in _VIDEO_QUALITY_VALUE_TO_LABEL.items()}


def video_quality_label(value) -> str:
    return _VIDEO_QUALITY_VALUE_TO_LABEL.get(str(value or "").strip(), "最高")


def video_quality_value(label) -> str:
    return _VIDEO_QUALITY_LABEL_TO_VALUE.get(str(label or "").strip(), "highest")


URL_TYPE_LABELS = {
    "video": "单个视频",
    "gallery": "单个图文",
    "user": "用户主页",
    "collection": "合集",
    "music": "音乐",
    "live": "直播（暂不支持）",
    "live_replay": "直播回放（暂不支持）",
    "short": "短链接",
}


def url_type_label(url_type: str) -> str:
    return URL_TYPE_LABELS.get(str(url_type or ""), "无法识别")


# ── helpers (mirrored from desktop_app.py) ──────────────────────────

def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def merge_dict(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def classify_error(exc: Exception) -> str:
    """Return a user-friendly Chinese error message based on exception type and content."""
    msg = str(exc).lower()
    name = type(exc).__name__.lower()

    # 登录态识别：2483 状态码 / "请先登录" / "用户未登录"（LoginRequiredError）
    if isinstance(exc, LoginRequiredError) or "login required (status_code=" in msg:
        return (
            "登录已过期，需要重新登录。\n\n"
            "请按以下步骤操作：\n"
            "1. 在浏览器中打开 https://www.douyin.com 并登录\n"
            "2. 按 F12 打开开发者工具 → Application → Cookies 复制新的 Cookie\n"
            "3. 在「⚙️ 设置」标签页点「✏️ 修改」→ 粘贴新 Cookie → 保存配置\n"
            "4. 重新执行下载"
        )

    cookie_keywords = ("cookie", "login", "auth", "token", "passport", "session", "verify",
                       "验证", "登录", "凭据")
    if any(kw in msg for kw in cookie_keywords) or any(kw in name for kw in ("auth", "cookie")):
        return (
            "Cookie 已失效或无效。\n\n"
            "请按以下步骤获取新的 Cookie：\n"
            "1. 在浏览器中打开 https://www.douyin.com 并登录\n"
            "2. 按 F12 打开开发者工具 → Application → Cookies\n"
            "3. 复制所有 Cookie 字符串，粘贴到程序的 Cookie 输入框\n"
            "4. 重新执行下载"
        )

    network_keywords = ("timeout", "connect", "resolve", "dns", "network", "socket",
                        "refused", "unreachable", "eof", "reset", "断", "超时", "网络",
                        "connection", "proxy")
    if any(kw in msg for kw in network_keywords) or any(kw in name for kw in ("timeout", "connection", "proxy", "dns")):
        return (
            "网络连接失败。\n\n"
            "可能的原因和解决方法：\n"
            "• 网络不通：请检查网络连接是否正常\n"
            "• 代理问题：如果设置了代理，请检查代理地址和端口\n"
            "• DNS 解析失败：尝试更换 DNS 服务器\n"
            "• 抖音服务异常：稍后重试"
        )

    rate_keywords = ("rate", "limit", "too many", "429", "frequency", "频繁", "限流", "频控")
    if any(kw in msg for kw in rate_keywords):
        return (
            "请求过于频繁，已触发抖音限流。\n\n"
            "解决方法：\n"
            "• 降低线程数（建议从 1-2 开始）\n"
            "• 等待几分钟后重试\n"
            "• 如果持续被限流，可能需要更换 Cookie"
        )

    url_keywords = ("unsupported url", "无法识别", "不支持", "unrecognized", "invalid url")
    if any(kw in msg for kw in url_keywords):
        return (
            "无法识别此链接格式。\n\n"
            "请确认链接是以下格式之一：\n"
            "• 抖音分享链接：https://v.douyin.com/...\n"
            "• 用户主页：https://www.douyin.com/user/...\n"
            "• 视频链接：https://www.douyin.com/video/..."
        )

    perm_keywords = ("permission", "denied", "access", "readonly", "权限", "拒绝", "只读",
                     "mkdir", "directory", "folder")
    if any(kw in msg for kw in perm_keywords):
        return (
            "无法写入下载目录。\n\n"
            "请检查：\n"
            "• 下载目录是否存在且可写入\n"
            "• 磁盘空间是否充足\n"
            "• 目录路径是否包含非法字符"
        )

    if "empty" in msg and "200" in msg:
        return (
            "抖音返回了空响应（可能是反爬保护）。\n\n"
            "解决方法：\n"
            "• 确保 Cookie 是最新且有效的\n"
            "• 尝试启用「浏览器兜底」选项\n"
            "• 降低下载线程数\n"
            "• 等待一段时间后重试"
        )

    return f"执行出错：{exc}\n\n请检查日志获取详细信息。如问题持续，可尝试：\n• 检查 Cookie 是否有效\n• 降低线程数\n• 更换代理"


def default_download_dir() -> str:
    return str(Path.home() / "Desktop" / "抖音" / "Downloaded")


def human_size(value: int | None) -> str:
    if value is None or value <= 0:
        return "未知"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


# ── label maps ──────────────────────────────────────────────────────

OPERATION_LABELS = {
    "download": "下载作品",
}
OPERATION_VALUES = {label: value for value, label in OPERATION_LABELS.items()}

MODE_LABELS = {
    "post": "主页作品",
    "like": "喜欢作品",
    "mix": "合集作品",
    "music": "音乐原声作品",
    "collect": "收藏作品",
    "collectmix": "收藏合集",
}
MODE_VALUES = {label: value for value, label in MODE_LABELS.items()}


def operation_label(value: str) -> str:
    return OPERATION_LABELS.get(value, value)


def operation_value(label: str) -> str:
    return OPERATION_VALUES.get(label, label)


def mode_label(value: str) -> str:
    return MODE_LABELS.get(value, value)


def mode_value(label: str) -> str:
    return MODE_VALUES.get(label, label)


# ── I/O adapters ────────────────────────────────────────────────────

class QueueWriter(io.TextIOBase):
    def __init__(self, output_queue: queue.Queue):
        self.output_queue = output_queue

    def write(self, value):
        if value:
            self.output_queue.put(str(value))
        return len(value or "")

    def flush(self):
        return None


class DesktopDownloadReporter:
    def __init__(self, output_queue: queue.Queue, pause_event: threading.Event,
                 cancel_event: threading.Event):
        self.output_queue = output_queue
        self.pause_event = pause_event
        self.cancel_event = cancel_event

    def update_step(self, step: str, detail: str = "") -> None:
        message = f"{step}：{detail}" if detail else step
        self.output_queue.put(("__STATUS__", message))

    def set_item_total(self, total: int, detail: str = "") -> None:
        message = f"{detail}，共 {total} 项" if detail else f"共 {total} 项"
        self.output_queue.put(("__STATUS__", message))

    def advance_item(self, status: str, detail: str = "") -> None:
        self.output_queue.put(("__STATUS__", f"{detail} {status}".strip()))

    def on_file_progress(self, file_name: str, written: int, expected_size: int | None) -> None:
        self.output_queue.put(("__FILE_PROGRESS__", file_name, written, expected_size))

    def should_pause(self) -> bool:
        return self.pause_event.is_set()

    def should_cancel(self) -> bool:
        return self.cancel_event.is_set()


# ══════════════════════════════════════════════════════════════════════
# Controller
# ══════════════════════════════════════════════════════════════════════

class AppController:
    """Owns all mutable state and business logic; the UI layer reads / calls this."""

    def __init__(self, project_root: Path, app_config: Path, app_settings: Path, log_cb: Callable):
        self.project_root = project_root
        self.app_config = app_config
        self.app_settings = app_settings
        self.log = log_cb  # callback: log(text: str)

        # ── output / threading ────────────────────────────────────
        self.output_queue: queue.Queue = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self.comments_worker: Optional[threading.Thread] = None
        self.user_worker: Optional[threading.Thread] = None
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()

        # ── config ─────────────────────────────────────────────────
        self.config_data = self._load_initial_config()

        # ── preview state ──────────────────────────────────────────
        self.preview_items: List[Any] = []
        self.preview_item_by_iid: Dict[str, Any] = {}
        self._aweme_id_to_iid: Dict[str, str] = {}  # O(1) reverse lookup
        self._comment_images: Dict[str, Any] = {}
        self._comments_aweme_id: str = ""
        self.user_preview_items: List[Any] = []
        self.user_preview_item_by_iid: Dict[str, Any] = {}
        self.active_mode_value = "post"

        # ── busy callback (set by UI) ─────────────────────────────
        self._busy_cb: Optional[Callable] = None
        self._user_busy_cb: Optional[Callable] = None

    # ── cookie helper ───────────────────────────────────────────────

    def _load_cookies_from_file(self) -> Dict[str, str]:
        """Read cookies from .cookies.json, falling back to config.yml."""
        cookie_file = self.project_root / ".cookies.json"
        if cookie_file.exists():
            try:
                data = json.loads(cookie_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    from utils.cookie_utils import sanitize_cookies
                    return sanitize_cookies(data)
            except Exception:
                pass
        cookie_str = (self.config_data.get("cookie") or "").strip()
        if cookie_str:
            from utils.cookie_utils import parse_cookie_header, sanitize_cookies
            return sanitize_cookies(parse_cookie_header(cookie_str))
        return {}

    def _inject_cookies_into_config(self, cfg: "ConfigLoader") -> None:
        """Patch a ConfigLoader's config so get_cookies() returns real cookies."""
        cookies = self._load_cookies_from_file()
        if cookies:
            cfg.config["cookies"] = cookies
            self.log(f"Cookie 已加载：{len(cookies)} 项\n")
        else:
            self.log("警告：Cookie 为空，所有请求可能失败！请先在设置页粘贴 Cookie 并保存。\n")

    # ── config I/O ──────────────────────────────────────────────────

    def _load_initial_config(self) -> dict:
        base = read_yaml(self.project_root / "config.example.yml")
        config = merge_dict(base, read_yaml(self.project_root / "config.yml"))
        if config:
            return config
        return base

    @staticmethod
    def config_to_yaml(config: dict) -> str:
        return yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=100000)

    def get_yaml_config(self, raw: str) -> dict:
        if not raw.strip():
            return {}
        loaded = yaml.safe_load(raw)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError("完整 YAML 必须是一个 YAML 对象。")
        return loaded

    def collect_config(self, form_values: dict) -> dict:
        """Build final config dict from form values."""
        config = merge_dict(self.config_data, {})

        modes = form_values.get("modes", ["post"])
        if not modes:
            modes = ["post"]
        primary_mode = modes[0]
        limit = max(0, int(form_values.get("limit") or 0))
        number = {
            "post": 0, "like": 0, "allmix": 0, "mix": 0,
            "music": 0, "collect": 0, "collectmix": 0,
        }
        number[primary_mode] = limit
        increase = {
            "post": False, "like": False, "allmix": False, "mix": False, "music": False,
        }
        if primary_mode in increase:
            increase[primary_mode] = bool(form_values.get("increase"))

        cookie_value = str(form_values.get("cookie", "")).strip()
        form_config = {
            "link": form_values.get("links", []),
            "path": form_values.get("path") or default_download_dir(),
            "cookie": cookie_value,
            "mode": modes,
            "number": number,
            "increase": increase,
            "thread": 3,  # hardcoded — optimal for Douyin anti-bot
            "retry_times": max(0, int(form_values.get("retry") or 3)),
            "proxy": "",
            "database": True,
            "database_path": str(self.project_root / "dy_downloader.db"),
            "cover": bool(form_values.get("cover", True)),
            "music": bool(form_values.get("music", False)),
            "avatar": bool(form_values.get("avatar", True)),
            "json": bool(form_values.get("json", True)),
            "homepage_screenshot": bool(form_values.get("homepage_screenshot", False)),
            "live_photo_merge": bool(form_values.get("live_photo_merge", True)),
            "video_quality": video_quality_value(form_values.get("video_quality")),
            "browser_fallback": {
                "enabled": bool(form_values.get("browser_fallback", True)),
                "headless": False,
                "max_scrolls": 240,
                "idle_rounds": 8,
                "wait_timeout_seconds": 600,
            },
            "progress": {"quiet_logs": True},
        }
        merged = merge_dict(config, form_config)

        if cookie_value:
            merged.pop("cookies", None)
        elif isinstance(merged.get("cookies"), dict):
            placeholder_values = {
                "YOUR_MS_TOKEN", "YOUR_TTWID", "YOUR_ODIN_TT",
                "YOUR_CSRF_TOKEN", "YOUR_SID_GUARD",
            }
            if all(str(v) in placeholder_values for v in merged["cookies"].values()):
                merged.pop("cookies", None)
        return merged

    def save_config(self, form_values: dict) -> dict:
        config = self.collect_config(form_values)

        # Persist cookies to .cookies.json (survives restart)
        cookie_value = str(form_values.get("cookie", "")).strip()
        if cookie_value:
            try:
                from auth import CookieManager
                from utils.cookie_utils import parse_cookie_header, sanitize_cookies
                cm = CookieManager(str(self.project_root / ".cookies.json"))
                parsed = sanitize_cookies(parse_cookie_header(cookie_value))
                if parsed:
                    cm.set_cookies(parsed)
                    self.log(f"Cookie 已保存到 {self.project_root / '.cookies.json'} ({len(parsed)} 项)\n")
            except Exception as exc:
                self.log(f"Cookie 保存失败：{exc}\n")

        # Strip cookies from YAML (they live in .cookies.json)
        saveable = {k: v for k, v in config.items() if k not in ("cookie", "cookies")}
        self.app_config.write_text(
            yaml.safe_dump(saveable, allow_unicode=True, sort_keys=False, width=100000),
            encoding="utf-8",
        )
        self.app_settings.write_text(
            json.dumps({"last_config": str(self.app_config)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.log(f"配置已保存：{self.app_config}\n")
        return config

    # ── preview ─────────────────────────────────────────────────────

    def start_preview(self, form_values: dict, mode: str):
        config = self.save_config(form_values)
        if not config.get("link"):
            raise ValueError("请至少输入一个抖音链接。")
        self.active_mode_value = mode_value(mode)
        self.preview_items = []
        self.preview_item_by_iid = {}
        self._aweme_id_to_iid = {}
        self.worker = threading.Thread(target=self._run_preview_thread, daemon=True)
        self.worker.start()

    def _run_preview_thread(self):
        try:
            items = asyncio.run(self._preview_items_from_config())
            self.output_queue.put(("__PREVIEW_DONE__", len(items)))
        except Exception as exc:
            self.output_queue.put(("__LOG__", f"\n{classify_error(exc)}\n"))
        finally:
            self.output_queue.put(("__DONE__", None))

    async def _preview_items_from_config(self):
        from auth import CookieManager
        from config import ConfigLoader
        from core.preview_service import PreviewService
        from storage import Database

        cfg = ConfigLoader(str(self.app_config))
        self._inject_cookies_into_config(cfg)
        cookie_manager = CookieManager(str(self.project_root / ".cookies.json"))
        cookie_manager.set_cookies(cfg.get_cookies())
        service = PreviewService(cfg, cookie_manager)
        db = Database(str(self.project_root / "dy_downloader.db"))
        await db.initialize()
        collected = []
        try:
            for url in cfg.get_links():
                self.output_queue.put(("__STATUS__", f"解析：{url}"))
                try:
                    resolved, parsed = await service.classify_url(url)
                except Exception as exc:
                    self.output_queue.put(("__LOG__", f"无法识别链接：{url}（{exc}）\n"))
                    self.output_queue.put(("__URL_TYPE__", url, "无法识别"))
                    continue
                url_type = parsed.get("type") or ""
                self.output_queue.put(("__URL_TYPE__", url, url_type_label(url_type)))
                if url_type in ("live", "live_replay"):
                    self.output_queue.put(("__LIVE_UNSUPPORTED__", url_type_label(url_type)))
                    continue
                if url_type == "user":
                    self.output_queue.put((
                        "__USER_URL__",
                        str(parsed.get("sec_uid") or ""),
                    ))
                    continue
                result = await service.preview_url(resolved, mode=self.active_mode_value)
                entry = self._parse_history_entry(url, resolved, parsed, result)
                if entry:
                    try:
                        await db.add_parse_history(entry)
                    except Exception:  # noqa: BLE001
                        pass
                self.output_queue.put(("__LOG__",
                    f"解析完成：{result.source_type} / {result.author_name} / {len(result.items)} 个作品\n"))
                for item in result.items:
                    collected.append(item)
                    self.output_queue.put(("__PREVIEW_ITEM__", item))
        finally:
            await db.close()
            await service.close()
        return collected

    @staticmethod
    def _parse_history_entry(url, resolved, parsed, result) -> Optional[dict]:
        """把一次成功的解析转成历史记录（按内容 ID 去重）。"""
        url_type = parsed.get("type") or ""
        if url_type == "video":
            kind, content_id = "video", str(parsed.get("aweme_id") or "")
        elif url_type == "gallery":
            kind, content_id = "gallery", str(parsed.get("aweme_id") or "")
        elif url_type == "collection":
            kind, content_id = "collection", str(parsed.get("mix_id") or "")
        elif url_type == "music":
            kind, content_id = "music", str(parsed.get("music_id") or "")
        else:
            return None
        if not content_id:
            return None
        name = result.author_name or "未知"
        if result.items:
            first = result.items[0]
            if url_type in ("video", "gallery"):
                name = getattr(first, "title", "") or name
            elif url_type == "collection":
                name = getattr(first, "collection_name", "") or name
        return {
            "kind": kind,
            "content_id": content_id,
            "name": name,
            "original_url": url,
            "resolved_url": resolved,
            "author_name": result.author_name or "",
            "avatar_url": "",
        }

    # ── download ────────────────────────────────────────────────────

    def start_download(self, form_values: dict, selected_items: List[Any]):
        config = self.save_config(form_values)
        Path(config["path"]).mkdir(parents=True, exist_ok=True)
        self.pause_event.clear()
        self.cancel_event.clear()
        self.active_mode_value = (form_values.get("modes") or ["post"])[0]
        self.output_queue.put(("__LOG__", "\n开始执行...\n"))
        self.worker = threading.Thread(
            target=self._run_gui_download_thread, args=(selected_items,), daemon=True)
        self.worker.start()

    def _run_gui_download_thread(self, selected_items, event_prefix: str = ""):
        try:
            items = selected_items
            if not items:
                self.output_queue.put(("__LOG__", "未找到预览作品，先自动解析链接。\n"))
                items = asyncio.run(self._preview_items_from_config())
            if not items:
                self.output_queue.put(("__LOG__", "没有可下载的作品。\n"))
                return
            asyncio.run(self._download_preview_items(items, event_prefix=event_prefix))
            self.output_queue.put(("__LOG__", "\n任务结束。\n"))
        except Exception as exc:
            self.output_queue.put(("__LOG__", f"\n{classify_error(exc)}\n"))
        finally:
            self.output_queue.put(("__DONE__", None))

    async def _download_preview_items(self, items, event_prefix: str = ""):
        from auth import CookieManager
        from config import ConfigLoader
        from control import QueueManager, RateLimiter, RetryHandler
        from core.api_client import DouyinAPIClient
        from core.user_downloader import UserDownloader
        from storage import Database, FileManager

        cfg = ConfigLoader(str(self.app_config))
        self._inject_cookies_into_config(cfg)
        cookie_manager = CookieManager(str(self.project_root / ".cookies.json"))
        api_client = DouyinAPIClient(cfg.get_cookies(), proxy=(cfg.get("proxy") or None))
        database = Database(cfg.get("database_path") or str(self.project_root / "dy_downloader.db"))
        await database.initialize()
        reporter = DesktopDownloadReporter(self.output_queue, self.pause_event, self.cancel_event)
        downloader = UserDownloader(
            config=cfg, api_client=api_client,
            file_manager=FileManager(cfg.get("path") or default_download_dir()),
            cookie_manager=cookie_manager, database=database,
            rate_limiter=RateLimiter(),
            retry_handler=RetryHandler(max_retries=int(cfg.get("retry_times") or 3)),
            queue_manager=QueueManager(max_workers=1),
            progress_reporter=reporter,
        )
        total = len(items)
        success = failed = skipped = 0

        async def process_item(index, item):
            nonlocal success, failed, skipped
            if self.cancel_event.is_set():
                return
            while self.pause_event.is_set() and not self.cancel_event.is_set():
                await asyncio.sleep(0.2)
            aweme_id = str(getattr(item, "aweme_id", "") or "")
            row_event = ("__ROW_STATUS_BY_ID__" if not event_prefix
                         else f"__{event_prefix.upper()}_ROW_STATUS_BY_ID__")
            self.output_queue.put((row_event, aweme_id, "正在下载", None))
            self.output_queue.put(("__STATUS__", f"下载 {index}/{total}：{getattr(item, 'title', aweme_id)}"))
            if not await downloader._should_download(aweme_id):
                skipped += 1
                self.output_queue.put((row_event, aweme_id, "已存在", None))
            else:
                mode = self._mode_for_preview_item(item)
                ok = await downloader._download_aweme_assets(
                    item.raw,
                    getattr(item, "author_name", "unknown") or "unknown",
                    mode=mode,
                )
                if ok:
                    success += 1
                    self.output_queue.put((row_event, aweme_id, "已下载到本地", None))
                else:
                    failed += 1
                    status = "已终止" if self.cancel_event.is_set() else "失败"
                    self.output_queue.put((row_event, aweme_id, status, None))
            completed = success + failed + skipped
            self.output_queue.put(("__TOTAL_PROGRESS__", completed, total, success, failed, skipped))

        max_workers = max(1, int(cfg.get("thread") or 1))
        semaphore = asyncio.Semaphore(max_workers)

        async def guarded(index, item):
            async with semaphore:
                await process_item(index, item)

        try:
            tasks = [guarded(i, item) for i, item in enumerate(items, start=1)]
            await asyncio.gather(*tasks)
            if self.cancel_event.is_set():
                self.output_queue.put(("__STATUS__", "已终止"))
        finally:
            await api_client.close()
            await database.close()

    @staticmethod
    def _mode_for_preview_item(item):
        source_type = getattr(item, "source_type", "") or ""
        if source_type.startswith("user:"):
            return source_type.split(":", 1)[1]
        if source_type == "collection":
            return "mix"
        if source_type == "music":
            return "music"
        return None

    # ── pause / resume / stop ───────────────────────────────────────

    def pause(self):
        self.pause_event.set()

    def resume(self):
        self.pause_event.clear()

    def stop(self):
        self.cancel_event.set()
        self.pause_event.clear()

    def set_busy_callback(self, cb: Optional[Callable]):
        self._busy_cb = cb

    def _set_busy(self, busy: bool):
        if self._busy_cb:
            self._busy_cb(busy)

    def set_user_busy_callback(self, cb: Optional[Callable]):
        self._user_busy_cb = cb

    def _set_user_busy(self, busy: bool):
        if self._user_busy_cb:
            self._user_busy_cb(busy)

    # ── 用户主页页签 ───────────────────────────────────────────────

    def start_user_preview(self, form_values: dict):
        """在用户主页页签后台加载指定子模式的作品列表。"""
        if self.user_worker and self.user_worker.is_alive():
            return
        config = self.save_config(form_values)
        mode = (form_values.get("modes") or ["post"])[0]
        sec_uid = str(form_values.get("sec_uid") or "").strip()
        if not sec_uid:
            raise ValueError("缺少用户主页链接")
        self.user_preview_items = []
        self.user_preview_item_by_iid = {}
        self._set_user_busy(True)
        self.user_worker = threading.Thread(
            target=self._run_user_preview_thread,
            args=(sec_uid, mode),
            daemon=True,
        )
        self.user_worker.start()

    def _run_user_preview_thread(self, sec_uid: str, mode: str):
        try:
            asyncio.run(self._preview_user_items(sec_uid, mode))
        except Exception as exc:
            self.output_queue.put(("__LOG__", f"\n用户主页加载失败：{classify_error(exc)}\n"))
            self.output_queue.put(("__USER_PREVIEW_DONE__", 0))
        finally:
            self.output_queue.put(("__USER_BUSY__", False))

    async def _preview_user_items(self, sec_uid: str, mode: str):
        from auth import CookieManager
        from config import ConfigLoader
        from core.preview_service import PreviewService
        from storage import Database

        cfg = ConfigLoader(str(self.app_config))
        self._inject_cookies_into_config(cfg)
        cookie_manager = CookieManager(str(self.project_root / ".cookies.json"))
        cookie_manager.set_cookies(cfg.get_cookies())
        service = PreviewService(cfg, cookie_manager)
        db = Database(str(self.project_root / "dy_downloader.db"))
        await db.initialize()
        try:
            self.output_queue.put(("__STATUS__", "正在加载用户作品…"))
            result = await service.preview_url(
                f"https://www.douyin.com/user/{sec_uid}", mode=mode)
            try:
                await db.add_parse_history({
                    "kind": "user",
                    "content_id": sec_uid,
                    "name": result.author_name or "未知",
                    "original_url": f"https://www.douyin.com/user/{sec_uid}",
                    "resolved_url": f"https://www.douyin.com/user/{sec_uid}",
                    "author_name": result.author_name or "",
                    "avatar_url": result.avatar_url or "",
                })
                if result.avatar_url:
                    await self._cache_avatar(
                        result.avatar_url, sec_uid, service)
            except Exception:  # noqa: BLE001
                pass
            for item in result.items:
                self.user_preview_items.append(item)
                self.output_queue.put(("__USER_PREVIEW_ITEM__", item))
            self.output_queue.put(("__USER_PREVIEW_DONE__", len(result.items)))
        finally:
            await db.close()
            await service.close()

    async def _cache_avatar(self, url: str, sec_uid: str, service):
        """把用户头像下载到本地缓存，历史对话框离线也能显示。"""
        from pathlib import Path

        from storage import FileManager

        cache_dir = self.project_root / "cache" / "avatars"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{sec_uid}.jpg"
        if target.exists():
            return target
        try:
            session = await service.api_client.get_session()
            fm = FileManager(str(cache_dir))
            result = await fm.download_file(
                url,
                target,
                session,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                    "Referer": "https://www.douyin.com/",
                },
                return_saved_path=True,
            )
            return Path(result) if result else None
        except Exception:  # noqa: BLE001
            return None

    # ── 解析历史查询/删除（供历史对话框使用）─────────────────────────

    def fetch_link_history(self) -> List[dict]:
        return asyncio.run(self._fetch_parse_history(
            kinds=["video", "gallery", "collection", "music"]))

    def fetch_user_history(self) -> List[dict]:
        return asyncio.run(self._fetch_parse_history(kinds=["user"]))

    async def _fetch_parse_history(self, kinds: List[str]) -> List[dict]:
        from storage import Database

        db = Database(str(self.project_root / "dy_downloader.db"))
        await db.initialize()
        try:
            return await db.list_parse_history(kinds=kinds, limit=200)
        finally:
            await db.close()

    def delete_history_entries(self, ids: List[int]) -> int:
        return asyncio.run(self._delete_parse_history(ids))

    async def _delete_parse_history(self, ids: List[int]) -> int:
        from storage import Database

        db = Database(str(self.project_root / "dy_downloader.db"))
        await db.initialize()
        try:
            return await db.delete_parse_history(ids)
        finally:
            await db.close()

    def clear_history_kinds(self, kinds: List[str]) -> int:
        return asyncio.run(self._clear_parse_history(kinds))

    async def _clear_parse_history(self, kinds: List[str]) -> int:
        from storage import Database

        db = Database(str(self.project_root / "dy_downloader.db"))
        await db.initialize()
        try:
            total = 0
            for kind in kinds:
                total += await db.clear_parse_history(kind)
            return total
        finally:
            await db.close()

    def start_user_download(self, form_values: dict, selected_items: List[Any]):
        """从用户主页页签开始下载。"""
        config = self.save_config(form_values)
        Path(config["path"]).mkdir(parents=True, exist_ok=True)
        self.pause_event.clear()
        self.cancel_event.clear()
        self.output_queue.put(("__LOG__", "\n开始执行...\n"))
        self._set_user_busy(True)
        self.user_worker = threading.Thread(
            target=self._run_gui_download_thread,
            args=(selected_items, "user"),
            daemon=True,
        )
        self.user_worker.start()

    # ── 评论浏览 ───────────────────────────────────────────────────

    def start_comments_load(self, aweme_id: str):
        """后台线程拉取单个作品的评论并生成缩略图。"""
        if self.comments_worker and self.comments_worker.is_alive():
            return
        self._comments_aweme_id = str(aweme_id or "")
        self._comment_images = {}
        self.output_queue.put(("__COMMENT_BUSY__", True))
        self.comments_worker = threading.Thread(
            target=self._run_comments_thread,
            args=(self._comments_aweme_id,),
            daemon=True,
        )
        self.comments_worker.start()

    def _run_comments_thread(self, aweme_id: str):
        try:
            asyncio.run(self._load_comments(aweme_id))
        except Exception as exc:
            self.output_queue.put(("__LOG__", f"\n评论加载失败：{classify_error(exc)}\n"))
            self.output_queue.put(("__COMMENT_BUSY__", False))
            self.output_queue.put(("__COMMENTS_ERROR__", "评论加载失败，请查看日志或稍后重试"))

    async def _load_comments(self, aweme_id: str):
        from core.api_client import DouyinAPIClient
        from core.comment_media import (
            CommentMediaDownloader,
            collect_all_comment_images,
        )
        from core.comments_collector import CommentsCollector
        from storage import FileManager, MetadataHandler

        cookies = self._load_cookies_from_file()
        if not cookies:
            self.output_queue.put(("__LOG__", "警告：Cookie 为空，评论加载可能失败。\n"))
        api_client = DouyinAPIClient(cookies, proxy=(self.config_data.get("proxy") or None))
        cache_root = self.project_root / "cache" / "comments" / str(aweme_id)
        thumbs_dir = cache_root / "thumbs"
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        try:
            collector = CommentsCollector(api_client, MetadataHandler())
            self.output_queue.put(("__STATUS__", "正在加载评论…"))
            comments = None
            for attempt in range(3):
                comments = await collector.collect(str(aweme_id))
                if comments is not None:
                    break
                if attempt < 2:
                    self.output_queue.put((
                        "__STATUS__",
                        f"评论加载被限流，正在重试（{attempt + 2}/3）…"))
                    await asyncio.sleep(2 + attempt * 3)
            if comments is None:
                self.output_queue.put(("__COMMENTS_ERROR__", "评论加载失败（可能被限流），请稍后重试"))
                return

            nickname_map = {
                str(c.get("cid") or ""):
                ((c.get("user") or {}).get("nickname") or "匿名")
                for c in comments if isinstance(c, dict)
            }
            for comment in comments:
                if isinstance(comment, dict):
                    self.output_queue.put(("__COMMENT_ITEM__", self._comment_display(comment)))

            images = collect_all_comment_images(comments)
            downloader = CommentMediaDownloader(FileManager(str(thumbs_dir)), api_client)
            failed_thumbs = 0
            total = len(images)
            for order, image in enumerate(images, start=1):
                key = f"{image.comment_id}_{image.index}"
                self._comment_images[key] = image.to_dict()
                thumb_path = await self._make_thumbnail(
                    downloader, image, thumbs_dir, key)
                if thumb_path is None:
                    failed_thumbs += 1
                nickname = nickname_map.get(str(image.comment_id), "匿名")
                self.output_queue.put((
                    "__COMMENT_THUMB__",
                    image.comment_id,
                    image.index,
                    str(thumb_path) if thumb_path else None,
                    image.is_live,
                    nickname,
                ))
                if order % 20 == 0 or order == total:
                    self.output_queue.put((
                        "__STATUS__", f"评论图片缩略图 {order}/{total}"))
            self.output_queue.put(("__COMMENTS_DONE__", len(comments), total, failed_thumbs))
        finally:
            await api_client.close()

    @staticmethod
    def _comment_display(comment: dict) -> dict:
        import time

        from core.comment_media import extract_comment_images

        user = comment.get("user") or {}
        try:
            timestamp = int(comment.get("create_time") or 0)
            time_text = (time.strftime("%Y-%m-%d %H:%M", time.localtime(timestamp))
                         if timestamp > 0 else "")
        except (TypeError, ValueError):
            time_text = ""
        images = extract_comment_images(comment)
        return {
            "cid": str(comment.get("cid") or ""),
            "nickname": user.get("nickname") or "匿名",
            "time": time_text,
            "ip_label": comment.get("ip_label") or "",
            "digg_count": int(comment.get("digg_count") or 0),
            "text": comment.get("text") or "",
            "image_count": len(images),
            "live_image_count": sum(1 for image in images if image.is_live),
        }

    async def _make_thumbnail(self, downloader, image, thumbs_dir, key):
        """下载缩略图并转成 PNG（Tkinter 可直接显示）。"""
        from pathlib import Path

        url = image.preview_url or (image.urls[-1] if image.urls else "")
        if not url:
            return None
        from core.comment_media import infer_image_extension

        raw_path = thumbs_dir / f"{key}{infer_image_extension(url)}"
        if not raw_path.exists():
            await downloader.download_preview(url, raw_path)
        if not raw_path.exists():
            return None
        png_path = thumbs_dir / f"{key}.png"
        try:
            from PIL import Image

            with Image.open(raw_path) as img:
                img.save(png_path, format="PNG")
            return png_path
        except Exception:
            return None

    # ── 评论图片下载 ───────────────────────────────────────────────

    def start_comment_image_download(self, image_refs: List[dict], save_dir: str):
        if self.comments_worker and self.comments_worker.is_alive():
            return
        self.output_queue.put(("__COMMENT_BUSY__", True))
        self.comments_worker = threading.Thread(
            target=self._run_comment_dl_thread,
            args=(list(image_refs), str(save_dir or "")),
            daemon=True,
        )
        self.comments_worker.start()

    def _run_comment_dl_thread(self, image_refs, save_dir: str):
        try:
            asyncio.run(self._download_comment_images(image_refs, save_dir))
        except Exception as exc:
            self.output_queue.put(("__LOG__", f"\n评论图片下载失败：{classify_error(exc)}\n"))
            self.output_queue.put(("__COMMENT_BUSY__", False))
            self.output_queue.put(("__COMMENT_DL_DONE__", 0, len(image_refs), save_dir))

    async def _download_comment_images(self, image_refs, save_dir: str):
        from core.api_client import DouyinAPIClient
        from core.comment_media import CommentImage, CommentMediaDownloader
        from storage import FileManager

        if not save_dir:
            raise ValueError("保存目录为空")
        cookies = self._load_cookies_from_file()
        api_client = DouyinAPIClient(cookies, proxy=(self.config_data.get("proxy") or None))
        try:
            images: List[CommentImage] = []
            for ref in image_refs:
                image_data = self._comment_images.get(
                    f"{ref.get('comment_id')}_{ref.get('index')}")
                if isinstance(image_data, dict):
                    images.append(CommentImage.from_dict(image_data))
            if not images:
                self.output_queue.put(("__LOG__", "没有可下载的评论图片。\n"))
                self.output_queue.put(("__COMMENT_DL_DONE__", 0, 0, save_dir))
                return
            downloader = CommentMediaDownloader(
                FileManager(str(Path(save_dir))), api_client)

            def _progress(current, total, success, failed, name):
                self.output_queue.put((
                    "__COMMENT_DL_PROGRESS__", current, total, success, failed, name))

            result = await downloader.download_comment_images(
                images, Path(save_dir), progress_callback=_progress)
            self.output_queue.put((
                "__COMMENT_DL_DONE__",
                len(result["success"]),
                len(result["failed"]),
                save_dir,
            ))
        finally:
            await api_client.close()

    # ── 评论图片放大预览 ───────────────────────────────────────────

    def start_comment_zoom(self, key: str, comment_id: str, index: int):
        if self.comments_worker and self.comments_worker.is_alive():
            return
        image_data = self._comment_images.get(f"{comment_id}_{index}")
        if not isinstance(image_data, dict):
            self.output_queue.put(("__COMMENT_ZOOM__", False, "", "图片信息缺失"))
            return
        urls = image_data.get("urls") or ([image_data.get("preview_url")] if image_data.get("preview_url") else [])
        if not urls:
            self.output_queue.put(("__COMMENT_ZOOM__", False, "", "图片地址缺失"))
            return
        url = urls[0]
        from core.comment_media import infer_image_extension

        cache_dir = (self.project_root / "cache" / "comments"
                     / str(self._comments_aweme_id) / "zoom")
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{key}{infer_image_extension(url)}"
        self.comments_worker = threading.Thread(
            target=self._run_zoom_thread,
            args=(url, str(cache_path)),
            daemon=True,
        )
        self.comments_worker.start()

    def _run_zoom_thread(self, url: str, cache_path: str):
        try:
            asyncio.run(self._download_zoom_image(url, cache_path))
        except Exception as exc:
            self.output_queue.put(("__COMMENT_ZOOM__", False, "", classify_error(exc)))

    async def _download_zoom_image(self, url: str, cache_path: str):
        from pathlib import Path

        from core.api_client import DouyinAPIClient
        from core.comment_media import CommentMediaDownloader
        from storage import FileManager

        cookies = self._load_cookies_from_file()
        api_client = DouyinAPIClient(cookies, proxy=(self.config_data.get("proxy") or None))
        try:
            downloader = CommentMediaDownloader(
                FileManager(str(Path(cache_path).parent)), api_client)
            path = await downloader.download_preview(url, Path(cache_path))
            self.output_queue.put((
                "__COMMENT_ZOOM__",
                bool(path),
                str(path) if path else "",
                "" if path else "下载失败",
            ))
        finally:
            await api_client.close()
