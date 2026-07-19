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
        self.pause_event = threading.Event()
        self.cancel_event = threading.Event()

        # ── config ─────────────────────────────────────────────────
        self.config_data = self._load_initial_config()

        # ── preview state ──────────────────────────────────────────
        self.preview_items: List[Any] = []
        self.preview_item_by_iid: Dict[str, Any] = {}
        self._aweme_id_to_iid: Dict[str, str] = {}  # O(1) reverse lookup
        self.active_mode_value = "post"

        # ── busy callback (set by UI) ─────────────────────────────
        self._busy_cb: Optional[Callable] = None

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

        cfg = ConfigLoader(str(self.app_config))
        self._inject_cookies_into_config(cfg)
        cookie_manager = CookieManager(str(self.project_root / ".cookies.json"))
        cookie_manager.set_cookies(cfg.get_cookies())
        service = PreviewService(cfg, cookie_manager)
        collected = []
        try:
            for url in cfg.get_links():
                self.output_queue.put(("__STATUS__", f"解析：{url}"))
                result = await service.preview_url(url, mode=self.active_mode_value)
                self.output_queue.put(("__LOG__",
                    f"解析完成：{result.source_type} / {result.author_name} / {len(result.items)} 个作品\n"))
                for item in result.items:
                    collected.append(item)
                    self.output_queue.put(("__PREVIEW_ITEM__", item))
        finally:
            await service.close()
        return collected

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

    def _run_gui_download_thread(self, selected_items):
        try:
            items = selected_items
            if not items:
                self.output_queue.put(("__LOG__", "未找到预览作品，先自动解析链接。\n"))
                items = asyncio.run(self._preview_items_from_config())
            if not items:
                self.output_queue.put(("__LOG__", "没有可下载的作品。\n"))
                return
            asyncio.run(self._download_preview_items(items))
            self.output_queue.put(("__LOG__", "\n任务结束。\n"))
        except Exception as exc:
            self.output_queue.put(("__LOG__", f"\n{classify_error(exc)}\n"))
        finally:
            self.output_queue.put(("__DONE__", None))

    async def _download_preview_items(self, items):
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
            self.output_queue.put(("__ROW_STATUS_BY_ID__", aweme_id, "正在下载", None))
            self.output_queue.put(("__STATUS__", f"下载 {index}/{total}：{getattr(item, 'title', aweme_id)}"))
            if getattr(item, "source_type", "") == "live":
                failed += 1
                self.output_queue.put(("__ROW_STATUS_BY_ID__", aweme_id, "暂不支持", None))
            elif not await downloader._should_download(aweme_id):
                skipped += 1
                self.output_queue.put(("__ROW_STATUS_BY_ID__", aweme_id, "已存在", None))
            else:
                mode = self._mode_for_preview_item(item)
                ok = await downloader._download_aweme_assets(
                    item.raw,
                    getattr(item, "author_name", "unknown") or "unknown",
                    mode=mode,
                )
                if ok:
                    success += 1
                    self.output_queue.put(("__ROW_STATUS_BY_ID__", aweme_id, "已下载到本地", None))
                else:
                    failed += 1
                    status = "已终止" if self.cancel_event.is_set() else "失败"
                    self.output_queue.put(("__ROW_STATUS_BY_ID__", aweme_id, status, None))
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
