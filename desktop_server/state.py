"""Stateful runtime for the embedded DouyinDownloader desktop backend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import yaml

from auth import CookieManager
from config import ConfigLoader
from control import QueueManager, RateLimiter, RetryHandler
from core import DouyinAPIClient, DownloaderFactory, LoginRequiredError, URLParser
from core.comment_export import export_comments_to_excel
from core.comment_media import CommentImage, CommentMediaDownloader, collect_all_comment_images
from core.comments_collector import CommentsCollector
from core.preview_service import PreviewItem, PreviewService
from core.user_downloader import UserDownloader
from desktop_server.events import EventBus, EventBusLogHandler, SpeedTracker
from storage import Database, FileManager, MetadataHandler
from tools.cookie_fetcher import filter_cookies, try_extract_ms_token
from utils.cookie_utils import parse_cookie_header, sanitize_cookies
from utils.logger import setup_logger
from utils.validators import extract_all_urls_from_text, extract_url_from_line, is_short_url, normalize_short_url

logger = setup_logger("DesktopServer")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_download_dir() -> str:
    return str(Path.home() / "Desktop" / "抖音" / "Downloaded")


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class _JobProgressAdapter:
    """Bridges BaseDownloader progress_reporter callbacks to EventBus + job state."""

    def __init__(
        self,
        runtime: "DesktopRuntime",
        job: Dict[str, Any],
        pause_event: asyncio.Event,
        cancel_event: asyncio.Event,
    ):
        self.runtime = runtime
        self.job = job
        self.pause_event = pause_event
        self.cancel_event = cancel_event

    def update_step(self, step: str, detail: str = "") -> None:
        self.job["step"] = f"{step}：{detail}" if detail else step
        self.runtime.emit_job_snapshot(self.job)

    def set_item_total(self, total: int, detail: str = "") -> None:
        if total > 0 and self.job.get("total", 0) == 0:
            self.job["total"] = int(total)
        if detail:
            self.job["step"] = detail
        self.runtime.emit_job_snapshot(self.job)

    def advance_item(self, status: str, detail: str = "", reason: str = "") -> None:
        if reason:
            self.job["step"] = f"{detail} ({reason})" if detail else reason
        self.runtime.emit_job_snapshot(self.job)

    def on_item_start(self, aweme_id: str = "", index: int = 0, total: int = 0, title: str = "") -> None:
        if total > 0:
            self.job["total"] = max(self.job.get("total", 0), int(total))
        self.job["current_file"] = title or aweme_id
        self.runtime.emit_job_snapshot(self.job)

    def on_item_progress(self, aweme_id: str, downloaded_bytes: int, total_bytes: int) -> None:
        speed = self.runtime.speed_tracker.record(f"{self.job['job_id']}:{aweme_id}", downloaded_bytes)
        self.job["speed_bps"] = speed
        self.job["current_written"] = int(downloaded_bytes or 0)
        self.job["current_total"] = int(total_bytes or 0)
        if total_bytes and total_bytes > downloaded_bytes and speed > 1024:
            self.job["eta_seconds"] = int((total_bytes - downloaded_bytes) / speed)
        else:
            self.job["eta_seconds"] = None

        item_entry = self.job.get("_item_map", {}).get(str(aweme_id))
        if item_entry is not None:
            item_entry["written"] = int(downloaded_bytes or 0)
            item_entry["total_bytes"] = int(total_bytes or 0)
            if total_bytes > 0:
                item_entry["progress"] = min(100.0, round(downloaded_bytes * 100.0 / total_bytes, 1))

        if self.runtime.event_bus.should_emit_progress(f"job:{self.job['job_id']}"):
            self.runtime.emit_job_snapshot(self.job)

    def on_file_progress(self, file_name: str, written: int, expected_size: Optional[int]) -> None:
        speed = self.runtime.speed_tracker.record(f"{self.job['job_id']}:{file_name}", written)
        self.job["current_file"] = file_name
        self.job["current_written"] = int(written or 0)
        self.job["current_total"] = int(expected_size or 0)
        self.job["speed_bps"] = speed
        if expected_size and expected_size > written and speed > 1024:
            self.job["eta_seconds"] = int((expected_size - written) / speed)
        if self.runtime.event_bus.should_emit_progress(f"job:{self.job['job_id']}"):
            self.runtime.emit_job_snapshot(self.job)

    def on_output_dir(self, path: str) -> None:
        if path:
            self.job["output_dir"] = path
            self.runtime.emit_job_snapshot(self.job)

    def on_author(self, nickname: Optional[str] = None, sec_uid: Optional[str] = None) -> None:
        if nickname:
            self.job["author_nickname"] = nickname
        if sec_uid:
            self.job["author_sec_uid"] = sec_uid
        self.runtime.emit_job_snapshot(self.job)

    def should_pause(self) -> bool:
        return self.pause_event.is_set()

    def should_cancel(self) -> bool:
        return self.cancel_event.is_set()


class DesktopRuntime:
    """Owns DB, config, preview cache, active download jobs, comments, and login."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.config_path = self.project_root / "config.yml"
        self.example_config_path = self.project_root / "config.example.yml"
        self.settings_path = self.project_root / "desktop_settings.json"
        self.cookie_path = self.project_root / ".cookies.json"
        self.db_path = self.project_root / "dy_downloader.db"
        self.cache_dir = self.project_root / "cache"
        self.thumb_cache_dir = self.cache_dir / "thumbs"
        self.avatar_cache_dir = self.cache_dir / "avatars"

        self.event_bus = EventBus()
        self.speed_tracker = SpeedTracker()
        self.db: Optional[Database] = None
        self.http_session: Optional[aiohttp.ClientSession] = None
        self._log_handler: Optional[EventBusLogHandler] = None

        # Previews
        self.preview_sessions: Dict[str, Dict[str, Any]] = {}
        self.preview_tasks: Dict[str, asyncio.Task] = {}

        # Jobs
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._job_controls: Dict[str, Dict[str, Any]] = {}
        self._job_tasks: Dict[str, asyncio.Task] = {}
        self._job_semaphore = asyncio.Semaphore(2)

        # Comments cache keyed by aweme_id
        self.comments_cache: Dict[str, Dict[str, Any]] = {}

        # Auth verification cache
        self._auth_cache: Optional[Dict[str, Any]] = None
        self._auth_cache_ts: float = 0.0

        # Browser login state
        self._login_task: Optional[asyncio.Task] = None
        self._login_extract_event: Optional[asyncio.Event] = None
        self._login_cancel_event: Optional[asyncio.Event] = None
        self.login_state: Dict[str, Any] = {"status": "idle", "message": ""}

    async def startup(self) -> None:
        self.event_bus.bind_loop(asyncio.get_running_loop())
        self.thumb_cache_dir.mkdir(parents=True, exist_ok=True)
        self.avatar_cache_dir.mkdir(parents=True, exist_ok=True)

        # Attach log forwarding handler to dy-downloader parent logger
        root_app_logger = logging.getLogger("dy-downloader")
        if self._log_handler is None:
            self._log_handler = EventBusLogHandler(self.event_bus)
            self._log_handler.setFormatter(logging.Formatter("%(message)s"))
            root_app_logger.addHandler(self._log_handler)

        self.db = Database(str(self.db_path))
        await self.db.initialize()
        await self._restore_terminal_jobs()

        connector = aiohttp.TCPConnector(limit=32, ttl_dns_cache=300)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=20),
        )
        logger.info("DesktopRuntime initialized (root=%s)", self.project_root)

    async def shutdown(self) -> None:
        # Cancel any running previews or login flow
        for task in list(self.preview_tasks.values()):
            if not task.done():
                task.cancel()
        if self._login_task and not self._login_task.done():
            if self._login_cancel_event:
                self._login_cancel_event.set()
            self._login_task.cancel()
        for jid, ctrl in list(self._job_controls.items()):
            ctrl["cancel_event"].set()
            ctrl["pause_event"].clear()
        for task in list(self._job_tasks.values()):
            if not task.done():
                task.cancel()
        if self._job_tasks:
            await asyncio.gather(*self._job_tasks.values(), return_exceptions=True)

        if self.http_session and not self.http_session.closed:
            await self.http_session.close()
            self.http_session = None
        if self.db is not None:
            await self.db.close()
            self.db = None

        if self._log_handler is not None:
            logging.getLogger("dy-downloader").removeHandler(self._log_handler)
            self._log_handler = None

    async def _restore_terminal_jobs(self) -> None:
        if self.db is None:
            return
        try:
            rows = await self.db.load_terminal_jobs(limit=100)
            for row in rows:
                jid = row["job_id"]
                self.jobs[jid] = {
                    "job_id": jid,
                    "title": row.get("author_nickname") or row.get("url") or jid,
                    "url": row.get("url") or "",
                    "source_kind": "urls",
                    "status": row.get("status") or "success",
                    "created_at": row.get("created_at") or "",
                    "started_at": row.get("started_at"),
                    "finished_at": row.get("finished_at"),
                    "total": int(row.get("total") or 0),
                    "completed": int(row.get("success") or 0)
                    + int(row.get("failed") or 0)
                    + int(row.get("skipped") or 0),
                    "success": int(row.get("success") or 0),
                    "failed": int(row.get("failed") or 0),
                    "skipped": int(row.get("skipped") or 0),
                    "error": row.get("error"),
                    "author_nickname": row.get("author_nickname"),
                    "author_sec_uid": row.get("author_sec_uid"),
                    "output_dir": "",
                    "current_file": "",
                    "current_written": 0,
                    "current_total": 0,
                    "speed_bps": 0.0,
                    "eta_seconds": None,
                    "step": "",
                    "items": [],
                    "can_retry_failed": False,
                }
        except Exception as exc:
            logger.warning("Failed to restore terminal jobs: %s", exc)

    # ── Settings & Cookies ──────────────────────────────────────────────

    def load_ui_preferences(self) -> Dict[str, Any]:
        defaults = {
            "theme": "light",
            "view_mode": "grid",
            "clipboard_watch": True,
            "window_geometry": None,
        }
        if not self.settings_path.exists():
            return defaults
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {**defaults, **data}
        except Exception:
            pass
        return defaults

    def save_ui_preferences(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        prefs = self.load_ui_preferences()
        prefs.update({k: v for k, v in patch.items() if v is not None})
        self.settings_path.write_text(
            json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return prefs

    def get_cookie_dict(self) -> Dict[str, str]:
        if self.cookie_path.exists():
            try:
                data = json.loads(self.cookie_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    return sanitize_cookies(data)
            except Exception:
                pass
        cfg_file = _read_yaml(self.config_path)
        raw_cookie = (cfg_file.get("cookie") or "").strip() if isinstance(cfg_file, dict) else ""
        if raw_cookie:
            return sanitize_cookies(parse_cookie_header(raw_cookie))
        return {}

    def get_cookie_string(self) -> str:
        cookies = self.get_cookie_dict()
        if not cookies:
            return ""
        return "; ".join(f"{k}={v}" for k, v in cookies.items())

    def save_cookie_string(self, raw_cookie: str) -> Dict[str, str]:
        parsed = sanitize_cookies(parse_cookie_header(raw_cookie.strip()))
        cm = CookieManager(str(self.cookie_path))
        if parsed:
            cm.set_cookies(parsed)
        elif self.cookie_path.exists():
            self.cookie_path.write_text("{}", encoding="utf-8")
        self._auth_cache = None
        return parsed

    def save_cookie_dict(self, cookies: Dict[str, str]) -> Dict[str, str]:
        cleaned = sanitize_cookies(cookies)
        cm = CookieManager(str(self.cookie_path))
        cm.set_cookies(cleaned)
        self._auth_cache = None
        return cleaned

    def build_config_loader(self, overrides: Optional[Dict[str, Any]] = None) -> ConfigLoader:
        cfg_arg = str(self.config_path) if self.config_path.exists() else None
        loader = ConfigLoader(cfg_arg)
        if not self.config_path.exists():
            loader.config["path"] = default_download_dir()
            loader.config["database_path"] = str(self.db_path)
        if overrides:
            loader.update(**overrides)
        cookies = self.get_cookie_dict()
        if cookies:
            loader.config["cookies"] = cookies
        return loader

    def get_settings_payload(self) -> Dict[str, Any]:
        loader = self.build_config_loader()
        cfg = deepcopy(loader.config)
        # Never inject placeholder cookies into UI
        cfg.pop("cookies", None)
        cfg.pop("cookie", None)
        cookie_dict = self.get_cookie_dict()
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
        essential = ["passport_csrf_token", "odin_tt", "sessionid"]
        found = sum(1 for k in essential if k in cookie_dict)
        return {
            "config": {
                "path": cfg.get("path") or default_download_dir(),
                "thread": int(cfg.get("thread") or 5),
                "retry_times": int(cfg.get("retry_times") or 3),
                "rate_limit": float(cfg.get("rate_limit") or 2),
                "proxy": str(cfg.get("proxy") or ""),
                "video_quality": str(cfg.get("video_quality") or "highest"),
                "video": bool(cfg.get("video", True)),
                "cover": bool(cfg.get("cover", False)),
                "music": bool(cfg.get("music", False)),
                "avatar": bool(cfg.get("avatar", False)),
                "json": bool(cfg.get("json", False)),
                "live_photo_merge": bool(cfg.get("live_photo_merge", True)),
                "homepage_screenshot": bool(cfg.get("homepage_screenshot", False)),
                "author_url": bool(cfg.get("author_url", False)),
                "download_pinned": bool(cfg.get("download_pinned", False)),
                "folderstyle": bool(cfg.get("folderstyle", True)),
                "group_by_mode": bool(cfg.get("group_by_mode", True)),
                "author_dir": str(cfg.get("author_dir") or "nickname"),
                "filename_template": str(cfg.get("filename_template") or "{date}_{title}_{id}"),
                "folder_template": str(cfg.get("folder_template") or "{date}_{title}_{id}"),
                "redownload_missing_files": bool(cfg.get("redownload_missing_files", True)),
                "increase": cfg.get("increase") or {"post": False, "like": False, "allmix": False, "mix": False, "music": False},
                "browser_fallback": cfg.get("browser_fallback") or {"enabled": True, "headless": False, "max_scrolls": 240, "idle_rounds": 8, "wait_timeout_seconds": 600},
                "comments": cfg.get("comments") or {"enabled": False, "include_replies": False, "max_comments": 0, "page_size": 20, "download_media": False},
                "live": cfg.get("live") or {"max_duration_seconds": 0, "chunk_size": 65536, "segment_seconds": 3600, "idle_timeout_seconds": 30},
                "notifications": cfg.get("notifications") or {"enabled": False, "on_success": True, "on_failure": True, "providers": []},
                "transcript": {
                    **(cfg.get("transcript") or {}),
                },
            },
            "cookie": {
                "has_cookie": bool(cookie_dict),
                "count": len(cookie_dict),
                "essential_present": found,
                "raw": cookie_str,
            },
            "preferences": self.load_ui_preferences(),
        }

    def save_settings_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cfg_patch = payload.get("config")
        if isinstance(cfg_patch, dict):
            # Ensure config.yml exists as a valid YAML baseline
            if not self.config_path.exists():
                base = _read_yaml(self.example_config_path)
                base.pop("cookies", None)
                base.pop("cookie", None)
                base["path"] = cfg_patch.get("path") or default_download_dir()
                base["database_path"] = str(self.db_path)
                self.config_path.write_text(
                    yaml.safe_dump(base, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
            loader = ConfigLoader(str(self.config_path))
            # Normalize mix/allmix if increase passed
            if isinstance(cfg_patch.get("increase"), dict):
                inc = dict(cfg_patch["increase"])
                if "mix" in inc:
                    inc["allmix"] = inc["mix"]
                cfg_patch["increase"] = inc
            loader.update(**cfg_patch)
            loader.config["database"] = True
            loader.config["database_path"] = str(self.db_path)
            loader.save()

        cookie_raw = payload.get("cookie_raw")
        if cookie_raw is not None:
            self.save_cookie_string(str(cookie_raw))

        prefs = payload.get("preferences")
        if isinstance(prefs, dict):
            self.save_ui_preferences(prefs)

        return self.get_settings_payload()

    # ── Auth & Browser Login ────────────────────────────────────────────

    async def get_auth_status(self, *, verify: bool = False) -> Dict[str, Any]:
        cookies = self.get_cookie_dict()
        essential = ["passport_csrf_token", "odin_tt", "sessionid"]
        missing = [k for k in essential if k not in cookies]
        now = time.monotonic()

        if not cookies:
            return {
                "has_cookie": False,
                "cookie_count": 0,
                "missing_keys": essential,
                "logged_in": False,
                "verified": False,
                "user": None,
                "login_flow": self.login_state,
            }

        if not verify and self._auth_cache is not None and (now - self._auth_cache_ts) < 180:
            return {
                **self._auth_cache,
                "has_cookie": True,
                "cookie_count": len(cookies),
                "missing_keys": missing,
                "login_flow": self.login_state,
            }

        if not verify:
            # Offline structural status without making a network round-trip
            return {
                "has_cookie": True,
                "cookie_count": len(cookies),
                "missing_keys": missing,
                "logged_in": len(missing) <= 1,
                "verified": False,
                "user": self._auth_cache.get("user") if self._auth_cache else None,
                "login_flow": self.login_state,
            }

        cfg = self.build_config_loader()
        proxy = (cfg.get("proxy") or "").strip() or None
        user_payload = None
        logged_in = False
        error_msg = ""
        async with DouyinAPIClient(cookies, proxy=proxy) as client:
            try:
                info = await client.get_self_info()
                if isinstance(info, dict) and (info.get("uid") or info.get("sec_uid")):
                    logged_in = True
                    avatar = PreviewService._first_url(
                        info.get("avatar_larger") or info.get("avatar_thumb")
                    )
                    user_payload = {
                        "uid": str(info.get("uid") or ""),
                        "sec_uid": str(info.get("sec_uid") or ""),
                        "nickname": str(info.get("nickname") or "抖音用户"),
                        "avatar_url": avatar,
                    }
            except LoginRequiredError as exc:
                error_msg = f"登录已过期：{exc.status_msg or '请重新登录'}"
            except Exception as exc:
                error_msg = str(exc)

        result = {
            "has_cookie": True,
            "cookie_count": len(cookies),
            "missing_keys": missing,
            "logged_in": logged_in,
            "verified": True,
            "user": user_payload,
            "error": error_msg,
            "login_flow": self.login_state,
        }
        self._auth_cache = result
        self._auth_cache_ts = time.monotonic()
        return result

    async def start_browser_login(self) -> Dict[str, Any]:
        if self._login_task and not self._login_task.done():
            return self.login_state

        self._login_extract_event = asyncio.Event()
        self._login_cancel_event = asyncio.Event()
        self.login_state = {
            "status": "waiting",
            "message": "正在打开抖音登录窗口，请在弹出的浏览器中扫码或账号登录…",
        }
        self.event_bus.emit_threadsafe("auth_login_state", self.login_state)
        self._login_task = asyncio.create_task(self._run_browser_login())
        return self.login_state

    def trigger_browser_login_extract(self) -> Dict[str, Any]:
        if self._login_extract_event is not None:
            self._login_extract_event.set()
        return self.login_state

    def cancel_browser_login(self) -> Dict[str, Any]:
        if self._login_cancel_event is not None:
            self._login_cancel_event.set()
        self.login_state = {"status": "idle", "message": "已取消登录"}
        self.event_bus.emit_threadsafe("auth_login_state", self.login_state)
        return self.login_state

    async def _run_browser_login(self) -> None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.login_state = {
                "status": "failed",
                "message": "未安装 Playwright 浏览器组件，请手动粘贴 Cookie。",
            }
            self.event_bus.emit_threadsafe("auth_login_state", self.login_state)
            return

        browser = None
        context = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                page = await context.new_page()
                observed_headers: List[str] = []
                observed_tokens: List[str] = []

                def _on_req(req):
                    try:
                        ch = (req.headers or {}).get("cookie")
                        if ch:
                            observed_headers.append(ch)
                    except Exception:
                        pass

                page.on("request", _on_req)
                await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)

                self.login_state = {
                    "status": "waiting",
                    "message": "请在浏览器中完成登录；登录成功后会自动识别，或点击「我已登录，立即提取」",
                }
                self.event_bus.emit_threadsafe("auth_login_state", self.login_state)

                deadline = time.monotonic() + 300
                captured: Dict[str, str] = {}
                while time.monotonic() < deadline:
                    if self._login_cancel_event and self._login_cancel_event.is_set():
                        return
                    if page.is_closed():
                        break
                    raw_cookies = await context.cookies("https://www.douyin.com")
                    cookie_map = {
                        c["name"]: c["value"]
                        for c in raw_cookies
                        if str(c.get("domain") or "").endswith("douyin.com")
                    }
                    has_session = bool(
                        cookie_map.get("sessionid")
                        and (cookie_map.get("uid_tt") or cookie_map.get("sid_tt"))
                    )
                    if has_session or (self._login_extract_event and self._login_extract_event.is_set()):
                        captured = sanitize_cookies(cookie_map)
                        ms_token = await try_extract_ms_token(
                            page, captured, observed_headers, observed_tokens
                        )
                        if ms_token and not captured.get("msToken"):
                            captured["msToken"] = ms_token
                        break
                    await asyncio.sleep(1.2)

                if not captured:
                    self.login_state = {
                        "status": "failed",
                        "message": "未能检测到登录 Cookie，请重试或手动复制 Cookie。",
                    }
                    self.event_bus.emit_threadsafe("auth_login_state", self.login_state)
                    return

                picked = filter_cookies(captured) or captured
                self.save_cookie_dict(picked)
                status = await self.get_auth_status(verify=True)
                self.login_state = {
                    "status": "success",
                    "message": f"登录成功！已保存 {len(picked)} 项 Cookie",
                }
                self.event_bus.emit_threadsafe("auth_login_state", self.login_state)
                self.event_bus.emit_threadsafe("auth_updated", status)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("Browser login error: %s", exc)
            self.login_state = {"status": "failed", "message": f"浏览器登录失败：{exc}"}
            self.event_bus.emit_threadsafe("auth_login_state", self.login_state)
        finally:
            try:
                if context is not None:
                    await context.close()
                if browser is not None:
                    await browser.close()
            except Exception:
                pass

    # ── URL inspection & Streaming Preview ──────────────────────────────

    def inspect_urls_text(self, raw_text: str) -> List[Dict[str, str]]:
        urls = extract_all_urls_from_text(raw_text)
        if not urls and raw_text.strip().lower() == "self":
            urls = ["https://www.douyin.com/user/self"]
        results: List[Dict[str, str]] = []
        for url in urls:
            if is_short_url(url):
                url_type = "short"
            else:
                parsed = URLParser.parse(url)
                url_type = (parsed or {}).get("type") or "unknown"
            results.append({"url": url, "type": url_type})
        return results

    def start_preview(
        self,
        *,
        preview_id: Optional[str] = None,
        urls: Optional[List[str]] = None,
        sec_uid: Optional[str] = None,
        mode: str = "post",
        limit: int = 0,
        start_time: str = "",
        end_time: str = "",
        increase: Optional[bool] = None,
    ) -> str:
        pid = (preview_id or "").strip() or uuid.uuid4().hex[:12]
        # Keep bounded preview sessions
        if len(self.preview_sessions) >= 15:
            oldest = next(iter(self.preview_sessions))
            self.preview_sessions.pop(oldest, None)

        self.preview_sessions[pid] = {
            "preview_id": pid,
            "items": [],
            "by_id": {},
            "meta": None,
            "status": "running",
        }
        task = asyncio.create_task(
            self._run_preview(
                preview_id=pid,
                urls=urls or [],
                sec_uid=sec_uid,
                mode=mode,
                limit=max(0, int(limit or 0)),
                start_time=(start_time or "").strip(),
                end_time=(end_time or "").strip(),
                increase=increase,
            )
        )
        self.preview_tasks[pid] = task
        return pid

    def cancel_preview(self, preview_id: str) -> bool:
        task = self.preview_tasks.get(preview_id)
        if task and not task.done():
            task.cancel()
            return True
        return False

    async def _run_preview(
        self,
        *,
        preview_id: str,
        urls: List[str],
        sec_uid: Optional[str],
        mode: str,
        limit: int,
        start_time: str,
        end_time: str,
        increase: Optional[bool],
    ) -> None:
        overrides: Dict[str, Any] = {}
        if sec_uid:
            overrides["number"] = {mode: limit}
            if start_time:
                overrides["start_time"] = start_time
            if end_time:
                overrides["end_time"] = end_time
            if increase is not None:
                overrides["increase"] = {mode: bool(increase)}

        cfg = self.build_config_loader(overrides=overrides)
        cm = CookieManager(str(self.cookie_path))
        cm.set_cookies(cfg.get_cookies())
        service = PreviewService(cfg, cm)
        session_store = self.preview_sessions[preview_id]

        async def _on_item(item: PreviewItem) -> None:
            session_store["items"].append(item)
            session_store["by_id"][item.aweme_id] = item
            await self.event_bus.publish(
                "preview_item",
                {"preview_id": preview_id, "item": item.to_summary_dict()},
            )

        try:
            targets = list(urls)
            if sec_uid:
                target_url = (
                    sec_uid
                    if sec_uid.startswith("http")
                    else f"https://www.douyin.com/user/{sec_uid}"
                )
                targets = [target_url]

            if not targets:
                raise RuntimeError("请先输入至少一个抖音链接或用户主页")

            meta_summary: Optional[Dict[str, Any]] = None
            for idx, raw_url in enumerate(targets, start=1):
                await self.event_bus.publish(
                    "preview_status",
                    {
                        "preview_id": preview_id,
                        "message": f"正在解析 ({idx}/{len(targets)})：{raw_url}",
                    },
                )
                resolved, parsed = await service.classify_url(raw_url)
                url_type = parsed.get("type") or ""

                # When Link Workbench encounters a user homepage without explicit creator mode,
                # still support direct previewing or allow UI to jump to Creator tab.
                result = await service.preview_url(resolved, mode=mode, on_item=_on_item)
                meta_summary = {
                    "preview_id": preview_id,
                    "url": raw_url,
                    "resolved_url": resolved,
                    "url_type": url_type,
                    "source_type": result.source_type,
                    "author_name": result.author_name,
                    "avatar_url": result.avatar_url,
                    "sec_uid": result.sec_uid,
                    "signature": result.signature,
                    "follower_count": result.follower_count,
                    "aweme_count": result.aweme_count,
                }
                await self.event_bus.publish("preview_meta", meta_summary)
                session_store["meta"] = meta_summary
                await self._record_parse_history(raw_url, resolved, parsed, result, service)

            session_store["status"] = "done"
            await self.event_bus.publish(
                "preview_done",
                {
                    "preview_id": preview_id,
                    "total": len(session_store["items"]),
                    "meta": meta_summary,
                },
            )
        except asyncio.CancelledError:
            session_store["status"] = "cancelled"
            await self.event_bus.publish(
                "preview_done",
                {"preview_id": preview_id, "total": len(session_store["items"]), "cancelled": True},
            )
        except Exception as exc:
            session_store["status"] = "error"
            logger.warning("Preview failed (%s): %s", preview_id, exc)
            await self.event_bus.publish(
                "preview_error",
                {"preview_id": preview_id, "error": str(exc)},
            )
        finally:
            self.preview_tasks.pop(preview_id, None)
            await service.close()

    async def _record_parse_history(
        self,
        raw_url: str,
        resolved: str,
        parsed: Dict[str, Any],
        result: Any,
        service: PreviewService,
    ) -> None:
        if self.db is None:
            return
        url_type = parsed.get("type") or ""
        if url_type == "user":
            kind = "user"
            content_id = result.sec_uid or str(parsed.get("sec_uid") or "")
            name = result.author_name or "未知"
        elif url_type in ("video", "gallery"):
            kind, content_id = url_type, str(parsed.get("aweme_id") or "")
            name = result.items[0].title if result.items else (result.author_name or "未知")
        elif url_type == "collection":
            kind, content_id = "collection", str(parsed.get("mix_id") or "")
            name = (
                result.items[0].collection_name
                if result.items and result.items[0].collection_name
                else (result.author_name or "合集")
            )
        elif url_type == "music":
            kind, content_id = "music", str(parsed.get("music_id") or "")
            name = result.author_name or "音乐"
        else:
            return

        if not content_id:
            return
        try:
            await self.db.add_parse_history(
                {
                    "kind": kind,
                    "content_id": content_id,
                    "name": name,
                    "original_url": raw_url,
                    "resolved_url": resolved,
                    "author_name": result.author_name or "",
                    "avatar_url": result.avatar_url or "",
                }
            )
            if kind == "user" and result.avatar_url and content_id:
                await self._cache_avatar(result.avatar_url, content_id, service)
        except Exception:
            pass

    async def _cache_avatar(self, url: str, sec_uid: str, service: PreviewService) -> None:
        safe_id = "".join(c for c in sec_uid if c.isalnum() or c in "-_")
        if not safe_id:
            return
        target = self.avatar_cache_dir / f"{safe_id}.jpg"
        if target.exists() and target.stat().st_size > 0:
            return
        try:
            session = await service.api_client.get_session()
            fm = FileManager(str(self.avatar_cache_dir))
            await fm.download_file(
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
        except Exception:
            pass

    # ── Download Task Management ────────────────────────────────────────

    def submit_download_job(
        self,
        *,
        preview_id: Optional[str] = None,
        aweme_ids: Optional[List[str]] = None,
        urls: Optional[List[str]] = None,
        mode: str = "post",
        title: str = "",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        selected_items: List[PreviewItem] = []
        if preview_id and preview_id in self.preview_sessions:
            sess = self.preview_sessions[preview_id]
            if aweme_ids:
                for aid in aweme_ids:
                    if aid in sess["by_id"]:
                        selected_items.append(sess["by_id"][aid])
            else:
                selected_items = list(sess["items"])

        url_list = [u.strip() for u in (urls or []) if u and u.strip()]
        if not selected_items and not url_list:
            raise ValueError("没有可下载的作品或链接")

        if selected_items:
            first_title = selected_items[0].author_name or selected_items[0].title
            job_title = title or (
                f"{first_title} 等 {len(selected_items)} 个作品"
                if len(selected_items) > 1
                else selected_items[0].title
            )
            source_kind = "items"
            job_url = selected_items[0].share_url or selected_items[0].aweme_id
            items_state = [
                {
                    "aweme_id": item.aweme_id,
                    "title": item.title,
                    "media_type": item.media_type,
                    "author_name": item.author_name,
                    "status": "pending",
                    "progress": 0.0,
                    "written": 0,
                    "total_bytes": 0,
                    "error": "",
                }
                for item in selected_items
            ]
            item_map = {entry["aweme_id"]: entry for entry in items_state}
        else:
            job_title = title or (
                f"{len(url_list)} 个链接任务" if len(url_list) > 1 else url_list[0]
            )
            source_kind = "urls"
            job_url = url_list[0]
            items_state = []
            item_map = {}

        cfg = self.build_config_loader(overrides=overrides)
        job: Dict[str, Any] = {
            "job_id": job_id,
            "title": job_title,
            "url": job_url,
            "source_kind": source_kind,
            "status": "pending",
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "total": len(selected_items) if selected_items else len(url_list),
            "completed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "error": None,
            "author_nickname": selected_items[0].author_name if selected_items else None,
            "author_sec_uid": selected_items[0].author_sec_uid if selected_items else None,
            "output_dir": str(cfg.get("path") or default_download_dir()),
            "current_file": "",
            "current_written": 0,
            "current_total": 0,
            "speed_bps": 0.0,
            "eta_seconds": None,
            "step": "排队中",
            "items": items_state,
            "can_retry_failed": False,
            "_item_map": item_map,
            "_selected_items": selected_items,
            "_failed_items": [],
            "_urls": url_list,
            "_mode": mode,
            "_overrides": overrides or {},
        }
        self.jobs[job_id] = job
        pause_ev = asyncio.Event()
        cancel_ev = asyncio.Event()
        self._job_controls[job_id] = {"pause_event": pause_ev, "cancel_event": cancel_ev}
        self.emit_job_snapshot(job)

        task = asyncio.create_task(self._execute_job(job_id))
        self._job_tasks[job_id] = task
        return self.serialize_job(job)

    def serialize_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [
            self.serialize_job(j)
            for j in sorted(self.jobs.values(), key=lambda x: x.get("created_at") or "", reverse=True)
        ]

    def emit_job_snapshot(self, job: Dict[str, Any]) -> None:
        self.event_bus.emit_threadsafe("job_update", self.serialize_job(job))

    def pause_job(self, job_id: str) -> bool:
        ctrl = self._job_controls.get(job_id)
        job = self.jobs.get(job_id)
        if not ctrl or not job or job["status"] not in ("pending", "running"):
            return False
        ctrl["pause_event"].set()
        job["status"] = "paused"
        job["step"] = "已暂停"
        self.emit_job_snapshot(job)
        return True

    def resume_job(self, job_id: str) -> bool:
        ctrl = self._job_controls.get(job_id)
        job = self.jobs.get(job_id)
        if not ctrl or not job or job["status"] != "paused":
            return False
        ctrl["pause_event"].clear()
        job["status"] = "running"
        job["step"] = "继续下载"
        self.emit_job_snapshot(job)
        return True

    def cancel_job(self, job_id: str) -> bool:
        ctrl = self._job_controls.get(job_id)
        job = self.jobs.get(job_id)
        if not ctrl or not job:
            return False
        ctrl["cancel_event"].set()
        ctrl["pause_event"].clear()
        if job["status"] == "pending":
            job["status"] = "cancelled"
            job["finished_at"] = _now_iso()
            job["step"] = "已取消"
        else:
            job["step"] = "正在终止…"
        self.emit_job_snapshot(job)
        return True

    def retry_failed_job(self, job_id: str) -> Dict[str, Any]:
        old = self.jobs.get(job_id)
        if not old:
            raise KeyError("任务不存在")
        failed_items = old.get("_failed_items") or []
        if not failed_items:
            raise ValueError("该任务没有可重试的失败项")
        temp_pid = f"retry_{uuid.uuid4().hex[:8]}"
        self.preview_sessions[temp_pid] = {
            "preview_id": temp_pid,
            "items": list(failed_items),
            "by_id": {it.aweme_id: it for it in failed_items},
            "status": "done",
        }
        return self.submit_download_job(
            preview_id=temp_pid,
            aweme_ids=[it.aweme_id for it in failed_items],
            title=f"重试：{old['title']}",
            overrides=old.get("_overrides"),
        )

    async def delete_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job["status"] in ("pending", "running", "paused"):
            self.cancel_job(job_id)
        self.jobs.pop(job_id, None)
        self._job_controls.pop(job_id, None)
        if self.db is not None:
            try:
                await self.db.delete_jobs([job_id])
            except Exception:
                pass
        self.event_bus.emit_threadsafe("job_deleted", {"job_id": job_id})
        return True

    async def _execute_job(self, job_id: str) -> None:
        job = self.jobs[job_id]
        ctrl = self._job_controls[job_id]
        pause_ev: asyncio.Event = ctrl["pause_event"]
        cancel_ev: asyncio.Event = ctrl["cancel_event"]
        adapter = _JobProgressAdapter(self, job, pause_ev, cancel_ev)

        async with self._job_semaphore:
            if cancel_ev.is_set():
                job["status"] = "cancelled"
                job["finished_at"] = _now_iso()
                self.emit_job_snapshot(job)
                return

            job["status"] = "running"
            job["started_at"] = _now_iso()
            job["step"] = "准备下载"
            self.emit_job_snapshot(job)

            cfg = self.build_config_loader(overrides=job.get("_overrides") or None)
            Path(cfg.get("path") or default_download_dir()).mkdir(parents=True, exist_ok=True)
            cm = CookieManager(str(self.cookie_path))
            cm.set_cookies(cfg.get_cookies())
            proxy = (cfg.get("proxy") or "").strip() or None
            threads = max(1, int(cfg.get("thread") or 5))
            rate_limiter = RateLimiter(max_per_second=float(cfg.get("rate_limit", 2) or 2))
            retry_handler = RetryHandler(max_retries=int(cfg.get("retry_times") or 3))
            queue_manager = QueueManager(max_workers=threads)
            file_manager = FileManager(cfg.get("path") or default_download_dir())

            api_client = DouyinAPIClient(cfg.get_cookies(), proxy=proxy)
            try:
                if job["source_kind"] == "items":
                    await self._run_items_job(
                        job,
                        job["_selected_items"],
                        cfg,
                        api_client,
                        file_manager,
                        cm,
                        rate_limiter,
                        retry_handler,
                        queue_manager,
                        adapter,
                        pause_ev,
                        cancel_ev,
                    )
                else:
                    await self._run_urls_job(
                        job,
                        job["_urls"],
                        job.get("_mode") or "post",
                        cfg,
                        api_client,
                        file_manager,
                        cm,
                        rate_limiter,
                        retry_handler,
                        queue_manager,
                        adapter,
                    )

                if cancel_ev.is_set():
                    job["status"] = "cancelled"
                    job["step"] = "已终止"
                elif job["failed"] > 0 and job["success"] == 0:
                    job["status"] = "failed"
                    job["step"] = "下载失败"
                else:
                    job["status"] = "success" if job["failed"] == 0 else "failed"
                    job["step"] = "已完成"
            except Exception as exc:
                logger.exception("Job %s failed", job_id)
                job["status"] = "failed"
                job["error"] = str(exc)
                job["step"] = f"出错：{exc}"
            finally:
                job["finished_at"] = _now_iso()
                job["speed_bps"] = 0.0
                job["eta_seconds"] = None
                job["can_retry_failed"] = bool(job.get("_failed_items"))
                self.speed_tracker.reset()
                await api_client.close()
                self._job_tasks.pop(job_id, None)
                self.emit_job_snapshot(job)
                if self.db is not None and job["status"] in ("success", "failed", "cancelled"):
                    try:
                        await self.db.upsert_job(
                            {
                                "job_id": job["job_id"],
                                "url": job["url"],
                                "status": job["status"],
                                "created_at": job["created_at"],
                                "started_at": job["started_at"],
                                "finished_at": job["finished_at"],
                                "total": job["total"],
                                "success": job["success"],
                                "failed": job["failed"],
                                "skipped": job["skipped"],
                                "error": job["error"],
                                "author_nickname": job.get("author_nickname"),
                                "author_sec_uid": job.get("author_sec_uid"),
                                "overrides": job.get("_overrides"),
                            }
                        )
                    except Exception as exc:
                        logger.warning("Failed to persist job %s: %s", job_id, exc)

    async def _run_items_job(
        self,
        job: Dict[str, Any],
        items: List[PreviewItem],
        cfg: ConfigLoader,
        api_client: DouyinAPIClient,
        file_manager: FileManager,
        cm: CookieManager,
        rate_limiter: RateLimiter,
        retry_handler: RetryHandler,
        queue_manager: QueueManager,
        adapter: _JobProgressAdapter,
        pause_ev: asyncio.Event,
        cancel_ev: asyncio.Event,
    ) -> None:
        downloader = UserDownloader(
            config=cfg,
            api_client=api_client,
            file_manager=file_manager,
            cookie_manager=cm,
            database=self.db,
            rate_limiter=rate_limiter,
            retry_handler=retry_handler,
            queue_manager=queue_manager,
            progress_reporter=adapter,
            job_id=job["job_id"],
        )

        # Partition regular awemes vs live / live_replay items
        sem = asyncio.Semaphore(max(1, int(cfg.get("thread") or 5)))

        async def _process(item: PreviewItem) -> None:
            while pause_ev.is_set() and not cancel_ev.is_set():
                await asyncio.sleep(0.25)
            if cancel_ev.is_set():
                return

            item_entry = job["_item_map"].get(item.aweme_id)
            if item_entry:
                item_entry["status"] = "downloading"
                self.emit_job_snapshot(job)

            job["current_file"] = item.title
            raw = item.raw or {}

            try:
                if raw.get("_kind") in ("live", "live_replay"):
                    parsed = raw.get("parsed") or {}
                    dl = DownloaderFactory.create(
                        raw["_kind"],
                        cfg,
                        api_client,
                        file_manager,
                        cm,
                        self.db,
                        rate_limiter,
                        retry_handler,
                        queue_manager,
                        progress_reporter=adapter,
                        job_id=job["job_id"],
                    )
                    if dl is None:
                        ok = False
                    else:
                        res = await dl.download(parsed)
                        ok = res.success > 0
                        if res.skipped > 0 and res.success == 0 and res.failed == 0:
                            job["skipped"] += 1
                            if item_entry:
                                item_entry["status"] = "skipped"
                                item_entry["progress"] = 100.0
                            job["completed"] = job["success"] + job["failed"] + job["skipped"]
                            self.emit_job_snapshot(job)
                            return
                else:
                    if not await downloader._should_download(item.aweme_id):
                        job["skipped"] += 1
                        if item_entry:
                            item_entry["status"] = "skipped"
                            item_entry["progress"] = 100.0
                        job["completed"] = job["success"] + job["failed"] + job["skipped"]
                        self.emit_job_snapshot(job)
                        return

                    mode = self._mode_for_preview_item(item)
                    ok = await downloader._download_aweme_assets(
                        raw,
                        item.author_name or "unknown",
                        mode=mode,
                        author_sec_uid=item.author_sec_uid or None,
                    )

                if ok:
                    job["success"] += 1
                    if item_entry:
                        item_entry["status"] = "success"
                        item_entry["progress"] = 100.0
                else:
                    job["failed"] += 1
                    job["_failed_items"].append(item)
                    if item_entry:
                        item_entry["status"] = "cancelled" if cancel_ev.is_set() else "failed"
                        item_entry["error"] = downloader.pop_item_reason(item.aweme_id, "failed") or ""
            except Exception as exc:
                job["failed"] += 1
                job["_failed_items"].append(item)
                if item_entry:
                    item_entry["status"] = "failed"
                    item_entry["error"] = str(exc)
            finally:
                self.speed_tracker.finish_file(f"{job['job_id']}:{item.aweme_id}")
                job["completed"] = job["success"] + job["failed"] + job["skipped"]
                self.emit_job_snapshot(job)

        async def _guarded(it: PreviewItem) -> None:
            async with sem:
                await _process(it)

        await asyncio.gather(*(_guarded(it) for it in items))

    async def _run_urls_job(
        self,
        job: Dict[str, Any],
        urls: List[str],
        mode: str,
        cfg: ConfigLoader,
        api_client: DouyinAPIClient,
        file_manager: FileManager,
        cm: CookieManager,
        rate_limiter: RateLimiter,
        retry_handler: RetryHandler,
        queue_manager: QueueManager,
        adapter: _JobProgressAdapter,
    ) -> None:
        cfg.update(mode=[mode])
        total_items = 0
        for raw_url in urls:
            if adapter.should_cancel():
                break
            extracted = extract_url_from_line(raw_url) or raw_url
            if is_short_url(extracted):
                resolved = await api_client.resolve_short_url(normalize_short_url(extracted))
                if not resolved:
                    job["failed"] += 1
                    continue
                extracted = resolved
            parsed = URLParser.parse(extracted)
            if not parsed:
                job["failed"] += 1
                continue
            dl = DownloaderFactory.create(
                parsed["type"],
                cfg,
                api_client,
                file_manager,
                cm,
                self.db,
                rate_limiter,
                retry_handler,
                queue_manager,
                progress_reporter=adapter,
                job_id=job["job_id"],
            )
            if dl is None:
                job["failed"] += 1
                continue
            res = await dl.download(parsed)
            total_items += res.total
            job["total"] = max(job["total"], total_items)
            job["success"] += res.success
            job["failed"] += res.failed
            job["skipped"] += res.skipped
            job["completed"] = job["success"] + job["failed"] + job["skipped"]
            if res.incomplete_reason and not job["error"]:
                job["error"] = res.incomplete_reason
            self.emit_job_snapshot(job)

    @staticmethod
    def _mode_for_preview_item(item: PreviewItem) -> Optional[str]:
        source_type = getattr(item, "source_type", "") or ""
        if source_type.startswith("user:"):
            return source_type.split(":", 1)[1]
        if source_type == "collection":
            return "mix"
        if source_type == "music":
            return "music"
        return None

    # ── Comments & Comment Gallery ──────────────────────────────────────

    async def load_comments(
        self,
        aweme_id: str,
        *,
        include_replies: bool = False,
        max_comments: int = 0,
    ) -> Dict[str, Any]:
        # Accept URL or bare aweme_id
        clean_id = str(aweme_id or "").strip()
        if clean_id.startswith("http") or "douyin.com" in clean_id:
            extracted = extract_url_from_line(clean_id) or clean_id
            async with DouyinAPIClient(self.get_cookie_dict()) as client:
                if is_short_url(extracted):
                    extracted = await client.resolve_short_url(normalize_short_url(extracted)) or extracted
            parsed = URLParser.parse(extracted) or {}
            clean_id = str(parsed.get("aweme_id") or clean_id)

        if not clean_id:
            raise ValueError("请输入有效的作品 ID 或链接")

        cfg = self.build_config_loader()
        proxy = (cfg.get("proxy") or "").strip() or None
        cookies = self.get_cookie_dict()
        async with DouyinAPIClient(cookies, proxy=proxy) as api_client:
            collector = CommentsCollector(
                api_client,
                MetadataHandler(),
                include_replies=include_replies,
                max_comments=max_comments,
                rate_limiter=RateLimiter(max_per_second=float(cfg.get("rate_limit", 2) or 2)),
            )
            comments = None
            for attempt in range(3):
                comments = await collector.collect(clean_id)
                if comments is not None:
                    break
                if attempt < 2:
                    await asyncio.sleep(1.5 + attempt * 2)

        if comments is None:
            raise RuntimeError("评论加载失败（可能被限流或需要有效 Cookie），请稍后重试")

        display_comments: List[Dict[str, Any]] = []
        nickname_map: Dict[str, str] = {}
        for idx, c in enumerate(comments):
            if not isinstance(c, dict):
                continue
            cid = str(c.get("cid") or c.get("comment_id") or f"no_cid_{idx}")
            user = c.get("user") or {}
            nick = str(user.get("nickname") or "匿名")
            nickname_map[cid] = nick
            ts = 0
            try:
                ts = int(c.get("create_time") or 0)
            except (TypeError, ValueError):
                pass
            time_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts > 0 else ""
            imgs = collect_all_comment_images([c])
            avatar = PreviewService._first_url(user.get("avatar_thumb"))
            display_comments.append(
                {
                    "cid": cid,
                    "nickname": nick,
                    "avatar_url": avatar,
                    "time": time_text,
                    "create_time": ts,
                    "ip_label": str(c.get("ip_label") or ""),
                    "digg_count": int(c.get("digg_count") or 0),
                    "text": str(c.get("text") or ""),
                    "image_count": len(imgs),
                    "live_image_count": sum(1 for i in imgs if i.is_live),
                }
            )

        raw_images = collect_all_comment_images(comments)
        image_map: Dict[str, CommentImage] = {}
        image_items: List[Dict[str, Any]] = []
        for img in raw_images:
            key = f"{img.comment_id}_{img.index}"
            image_map[key] = img
            image_items.append(
                {
                    "key": key,
                    "comment_id": img.comment_id,
                    "index": img.index,
                    "nickname": nickname_map.get(img.comment_id, "匿名"),
                    "preview_url": img.preview_url or (img.urls[-1] if img.urls else ""),
                    "origin_url": img.urls[0] if img.urls else img.preview_url,
                    "is_live": img.is_live,
                    "width": img.width,
                    "height": img.height,
                }
            )

        self.comments_cache[clean_id] = {
            "aweme_id": clean_id,
            "comments": display_comments,
            "images": image_items,
            "image_objects": image_map,
        }
        return {
            "aweme_id": clean_id,
            "comments": display_comments,
            "images": image_items,
            "total_comments": len(display_comments),
            "total_images": len(image_items),
        }

    async def download_comment_images(
        self,
        aweme_id: str,
        keys: List[str],
        save_dir: str,
    ) -> Dict[str, Any]:
        cached = self.comments_cache.get(str(aweme_id))
        if not cached:
            raise ValueError("请先加载该作品的评论")
        image_objects: Dict[str, CommentImage] = cached["image_objects"]
        selected = [image_objects[k] for k in keys if k in image_objects]
        if not selected:
            raise ValueError("未选中任何评论图片")

        cfg = self.build_config_loader()
        target_dir = Path(save_dir or (Path(cfg.get("path") or default_download_dir()) / "评论图片" / str(aweme_id)))
        target_dir.mkdir(parents=True, exist_ok=True)
        proxy = (cfg.get("proxy") or "").strip() or None

        async with DouyinAPIClient(self.get_cookie_dict(), proxy=proxy) as api_client:
            downloader = CommentMediaDownloader(FileManager(str(target_dir)), api_client)

            def _progress(current: int, total: int, success: int, failed: int, name: str) -> None:
                self.event_bus.emit_threadsafe(
                    "comment_download_progress",
                    {
                        "aweme_id": aweme_id,
                        "current": current,
                        "total": total,
                        "success": success,
                        "failed": failed,
                        "name": name,
                    },
                )

            result = await downloader.download_comment_images(
                selected, target_dir, progress_callback=_progress
            )

        return {
            "success": len(result.get("success", [])),
            "failed": len(result.get("failed", [])),
            "save_dir": str(target_dir),
        }

    def export_comments_excel(
        self,
        aweme_id: str,
        output_path: str,
        aweme_title: str = "",
    ) -> str:
        cached = self.comments_cache.get(str(aweme_id))
        if not cached:
            raise ValueError("请先加载评论再导出")
        comment_text_by_cid = {c["cid"]: c.get("text", "") for c in cached["comments"]}
        images_payload = [
            {
                "comment_id": img["comment_id"],
                "index": img["index"],
                "is_live": img["is_live"],
                "nickname": img["nickname"],
                "text": comment_text_by_cid.get(img["comment_id"], ""),
            }
            for img in cached["images"]
        ]
        ok = export_comments_to_excel(
            cached["comments"],
            images_payload,
            output_path,
            aweme_id=str(aweme_id),
            aweme_title=aweme_title,
        )
        if not ok:
            raise RuntimeError("Excel 导出失败，请检查文件是否被占用")
        return str(Path(output_path).resolve())
