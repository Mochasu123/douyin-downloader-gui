"""Headless Playwright page bridge for ArgusSecurityPlugin-gated Douyin APIs."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

from utils.logger import setup_logger

logger = setup_logger("PageBridge")

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)
_DOUYIN_HOME_URL = "https://www.douyin.com/"
_DROP_ALWAYS_PARAMS = frozenset({"a_bogus", "X-Bogus"})
_DROP_IF_EMPTY_PARAMS = frozenset({"uifid", "msToken"})

_FETCH_EVAL_JS = """async (req) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort("TIMEOUT"), req.timeoutMs || 25000);
    try {
        const init = {
            method: req.method || "GET",
            credentials: "include",
            headers: {
                "Accept": "application/json, text/plain, */*"
            },
            signal: controller.signal
        };
        if (req.method === "POST") {
            init.headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8";
            init.body = req.formBody || "";
        }
        const resp = await window.fetch(req.url, init);
        const text = await resp.text();
        return { http_status: resp.status, text };
    } catch (err) {
        if (err && (err.name === "AbortError" || String(err) === "TIMEOUT")) {
            return { error_code: "TIMEOUT", message: "window.fetch aborted on timeout" };
        }
        return { error_code: "FETCH_ERROR", message: String(err && err.message ? err.message : err) };
    } finally {
        clearTimeout(timer);
    }
}"""


@dataclass
class PageBridgeResponse:
    """Response shape expected by DouyinAPIClient._request_json_gated."""

    http_status: int
    body: Any
    text: str = ""


class PageBridgeError(RuntimeError):
    """Transport error tagged with ``page_bridge_code`` for DouyinAPIClient."""

    def __init__(self, code: str, message: str = ""):
        self.page_bridge_code = code
        super().__init__(message or f"page bridge error: {code}")


async def launch_chromium_browser(
    playwright: Any,
    *,
    headless: bool = True,
    proxy: Optional[str] = None,
) -> Any:
    """Launch system Edge/Chrome or bundled Playwright Chromium browser."""
    clean_proxy = str(proxy or "").strip()
    base_kwargs: Dict[str, Any] = {
        "headless": headless,
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    if clean_proxy:
        base_kwargs["proxy"] = {"server": clean_proxy}

    errors = []
    for channel in ("msedge", "chrome", None):
        kwargs = dict(base_kwargs)
        if channel is not None:
            kwargs["channel"] = channel
        try:
            browser = await playwright.chromium.launch(**kwargs)
            logger.info("Launched Playwright Chromium browser (channel=%s, headless=%s)", channel or "bundled", headless)
            return browser
        except Exception as exc:
            errors.append(f"{channel or 'bundled'}: {exc}")
    raise PageBridgeError(
        "BROWSER_UNAVAILABLE",
        f"无法启动浏览器通道 (msedge/chrome/chromium): {'; '.join(errors)}",
    )


class DesktopPageBridge:
    """Lazy, reusable Douyin browser-context fetch bridge for gated endpoints."""

    def __init__(
        self,
        cookie_provider: Callable[[], Dict[str, str]],
        proxy_provider: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        self._cookie_provider = cookie_provider
        self._proxy_provider = proxy_provider
        self._lock = asyncio.Lock()
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._page_loaded = False
        self._applied_cookie_fingerprint: Optional[Tuple[Tuple[str, str], ...]] = None
        self._applied_proxy: str = ""

    @staticmethod
    def build_request_url(path: str, params: Dict[str, Any]) -> str:
        """Build relative URL for Douyin web fetch, letting the SDK sign it."""
        filtered: Dict[str, Any] = {}
        for key, value in (params or {}).items():
            if key in _DROP_ALWAYS_PARAMS:
                continue
            if value is None:
                continue
            if key in _DROP_IF_EMPTY_PARAMS and str(value).strip() == "":
                continue
            filtered[key] = value
        normalized_path = path if path.startswith("/") else f"/{path}"
        query = urlencode(filtered)
        return f"{normalized_path}?{query}" if query else normalized_path

    def mark_cookies_dirty(self) -> None:
        """Force cookie reload onto the browser context before the next fetch."""
        self._applied_cookie_fingerprint = None

    async def fetch(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
    ) -> PageBridgeResponse:
        req_method = method.upper()
        req_url = self.build_request_url(path, params)
        form_body = urlencode(data or {}) if req_method == "POST" else ""

        last_exc: Optional[Exception] = None
        for attempt in range(2):
            page = await self._ensure_ready()
            try:
                raw = await page.evaluate(
                    _FETCH_EVAL_JS,
                    {
                        "url": req_url,
                        "method": req_method,
                        "formBody": form_body,
                        "timeoutMs": 25_000,
                    },
                )
            except Exception as exc:
                last_exc = exc
                logger.warning("PageBridge evaluate failed (attempt=%d/2): %s", attempt + 1, exc)
                async with self._lock:
                    await self._close_locked()
                continue

            if isinstance(raw, dict) and raw.get("error_code"):
                code = str(raw.get("error_code"))
                msg = str(raw.get("message") or code)
                if code == "TIMEOUT":
                    raise PageBridgeError("TIMEOUT", msg)
                last_exc = PageBridgeError("PAGE_LOAD_FAILED", msg)
                if attempt == 0:
                    async with self._lock:
                        self._page_loaded = False
                    continue
                raise last_exc

            status = int((raw or {}).get("http_status") or 0)
            text = str((raw or {}).get("text") or "")
            body: Any = None
            if text.strip():
                try:
                    body = json.loads(text)
                except Exception:
                    body = None
            return PageBridgeResponse(http_status=status, body=body, text=text)

        raise PageBridgeError(
            "PAGE_LOAD_FAILED",
            str(last_exc or "PageBridge 浏览器页面执行失败"),
        )

    async def _ensure_ready(self) -> Any:
        async with self._lock:
            proxy = str((self._proxy_provider() if self._proxy_provider else "") or "").strip()
            if self._browser is not None and proxy != self._applied_proxy:
                await self._close_locked()

            if self._playwright is None:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()

            if self._browser is None:
                self._browser = await launch_chromium_browser(
                    self._playwright,
                    headless=True,
                    proxy=proxy or None,
                )
                self._applied_proxy = proxy
                self._context = None
                self._page = None
                self._page_loaded = False

            if self._context is None:
                self._context = await self._browser.new_context(
                    user_agent=_DEFAULT_USER_AGENT,
                    locale="zh-CN",
                )
                self._page = None
                self._page_loaded = False
                self._applied_cookie_fingerprint = None

            if self._page is None or self._page.is_closed():
                self._page = await self._context.new_page()
                self._page_loaded = False

            cookies = dict(self._cookie_provider() or {})
            fingerprint = tuple(sorted((str(k), str(v)) for k, v in cookies.items() if k and v))

            need_nav = not self._page_loaded or fingerprint != self._applied_cookie_fingerprint
            if fingerprint != self._applied_cookie_fingerprint:
                await self._context.clear_cookies()
                if fingerprint:
                    cookie_entries = [
                        {"name": k, "value": v, "domain": ".douyin.com", "path": "/"}
                        for k, v in fingerprint
                    ]
                    await self._context.add_cookies(cookie_entries)
                self._applied_cookie_fingerprint = fingerprint

            if need_nav:
                try:
                    await self._page.goto(_DOUYIN_HOME_URL, wait_until="domcontentloaded", timeout=30_000)
                except Exception as exc:
                    raise PageBridgeError("PAGE_LOAD_FAILED", f"打开抖音主页失败: {exc}") from exc
                await self._wait_sdk_ready(self._page)
                self._page_loaded = True

            return self._page

    @staticmethod
    async def _wait_sdk_ready(page: Any) -> None:
        started = time.monotonic()
        while (time.monotonic() - started) < 4.0:
            try:
                ready = await page.evaluate(
                    """() => {
                        const hasSdk = Boolean(window.bdms || window.byted_acrawler);
                        const hasUifid = document.cookie.includes("UIFID") || document.cookie.includes("ttwid");
                        return document.readyState !== "loading" && hasSdk && hasUifid;
                    }"""
                )
                if ready and (time.monotonic() - started) >= 0.8:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.25)

    async def _close_locked(self) -> None:
        for obj, method in (
            (self._page, "close"),
            (self._context, "close"),
            (self._browser, "close"),
            (self._playwright, "stop"),
        ):
            if obj is not None:
                try:
                    await getattr(obj, method)()
                except Exception:
                    pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._page_loaded = False
        self._applied_cookie_fingerprint = None

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()
