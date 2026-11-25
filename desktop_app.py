#!/usr/bin/env python3
"""Desktop entry point for DouyinDownloader (PyWebView + embedded FastAPI)."""

from __future__ import annotations

import argparse
import ctypes
import io
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional


def _ensure_std_streams() -> None:
    """Guard against None stdout/stderr in PyInstaller --windowed builds."""
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()


_ensure_std_streams()


def bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def app_root() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent
    exe_dir = Path(sys.executable).resolve().parent
    for path in (exe_dir, *exe_dir.parents):
        if (path / "config.example.yml").exists() or (path / ".git").exists():
            return path
    return exe_dir


PROJECT_ROOT = app_root()
BUNDLED_ROOT = bundled_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

APP_SETTINGS = PROJECT_ROOT / "desktop_settings.json"


def _frontend_dist_dir() -> Path:
    candidate = BUNDLED_ROOT / "frontend" / "dist"
    if (candidate / "index.html").exists():
        return candidate
    return PROJECT_ROOT / "frontend" / "dist"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(port: int, timeout: float = 12.0) -> bool:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def _read_win32_clipboard() -> str:
    if sys.platform != "win32":
        return ""
    cf_unicode_text = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.GetClipboardData.argtypes = [ctypes.c_uint]
    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.restype = ctypes.c_bool
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    if not user32.OpenClipboard(None):
        return ""
    try:
        handle = user32.GetClipboardData(cf_unicode_text)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr) or ""
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


class NativeBridge:
    """Functions exposed to the web UI via window.pywebview.api."""

    def __init__(self) -> None:
        self.window = None

    def attach_window(self, window) -> None:
        self.window = window

    def pick_directory(self, initial_dir: str = "") -> Optional[str]:
        if self.window is None:
            return None
        import webview

        target_dir = initial_dir if initial_dir and Path(initial_dir).exists() else str(Path.home())
        result = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=target_dir)
        if isinstance(result, (list, tuple)) and result:
            return str(result[0])
        if isinstance(result, str) and result:
            return result
        return None

    def save_file_dialog(self, default_name: str = "comments.xlsx") -> Optional[str]:
        if self.window is None:
            return None
        import webview

        result = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=str(Path.home() / "Desktop"),
            save_filename=default_name or "comments.xlsx",
            file_types=("Excel 工作簿 (*.xlsx)",),
        )
        if isinstance(result, (list, tuple)) and result:
            return str(result[0])
        if isinstance(result, str) and result:
            return result
        return None

    def open_path(self, path: str) -> bool:
        try:
            p = Path(path)
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(p))
            return True
        except Exception:
            return False

    def reveal_in_explorer(self, path: str) -> bool:
        try:
            p = Path(path)
            if sys.platform == "win32":
                if p.is_file():
                    subprocess.Popen(["explorer", f"/select,{p}"])
                elif p.exists():
                    os.startfile(str(p))
            return True
        except Exception:
            return False

    def read_clipboard(self) -> str:
        try:
            return _read_win32_clipboard()
        except Exception:
            return ""


def _load_window_settings() -> dict:
    if not APP_SETTINGS.exists():
        return {}
    try:
        data = json.loads(APP_SETTINGS.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_window_geometry(window) -> None:
    try:
        data = _load_window_settings()
        data["window_rect"] = {
            "width": int(window.width),
            "height": int(window.height),
            "x": int(window.x),
            "y": int(window.y),
        }
        APP_SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _run_self_test() -> int:
    log_root = (
        Path(sys.executable).resolve().parent
        if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent
    )
    log_path = log_root / "desktop_self_test.log"
    lines = [
        f"frozen={getattr(sys, 'frozen', False)}",
        f"executable={sys.executable}",
        f"PROJECT_ROOT={PROJECT_ROOT}",
        f"BUNDLED_ROOT={BUNDLED_ROOT}",
    ]
    try:
        import asyncio
        from fastapi.testclient import TestClient

        from auth import CookieManager
        from cli.main import download_url, main_async
        from config import ConfigLoader
        from core import DouyinAPIClient, DownloaderFactory, URLParser
        from core.discovery import dump_hot_board, search_and_dump
        from core.preview_service import PreviewService
        from desktop_server.app import create_app
        from server.app import run_server
        from storage import Database

        assert callable(main_async)
        assert callable(download_url)
        assert ConfigLoader(None).get("path") is not None
        assert CookieManager is not None
        assert DouyinAPIClient is not None
        assert DownloaderFactory is not None
        assert URLParser is not None
        assert PreviewService is not None
        assert callable(dump_hot_board)
        assert callable(search_and_dump)
        assert callable(run_server)
        lines.append("core_imports=OK")

        dist_dir = _frontend_dist_dir()
        assert (dist_dir / "index.html").exists(), f"Missing frontend build: {dist_dir}"
        lines.append(f"frontend_dist=OK ({dist_dir})")

        test_db = PROJECT_ROOT / "desktop_self_test.sqlite"
        if test_db.exists():
            test_db.unlink()

        async def _db_test():
            db = Database(str(test_db))
            await db.initialize()
            await db.close()

        asyncio.run(_db_test())
        if test_db.exists():
            test_db.unlink()
        lines.append("sqlite=OK")

        app = create_app(PROJECT_ROOT, frontend_dist=dist_dir)
        with TestClient(app) as client:
            resp = client.get("/api/health")
            assert resp.status_code == 200
            assert resp.json().get("status") == "ok"
        lines.append("api_health=OK")

        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except Exception:
        lines.append("exception=")
        lines.append(traceback.format_exc())
        try:
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:
            pass
        return 1


def _run_web_mode(port: Optional[int], no_open: bool) -> int:
    import uvicorn
    from desktop_server.app import create_app

    chosen_port = port or _find_free_port()
    app = create_app(PROJECT_ROOT, frontend_dist=_frontend_dist_dir())
    if not no_open:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{chosen_port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=chosen_port, log_config=None)
    return 0


def _run_desktop_mode() -> int:
    import uvicorn
    import webview
    from desktop_server.app import create_app

    port = _find_free_port()
    app = create_app(PROJECT_ROOT, frontend_dist=_frontend_dist_dir())
    uv_config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None)
    server = uvicorn.Server(uv_config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not _wait_for_health(port, timeout=12.0):
        raise RuntimeError("Embedded desktop backend failed to start within timeout")

    saved = _load_window_settings()
    rect = saved.get("window_rect") if isinstance(saved.get("window_rect"), dict) else {}
    width = max(980, int(rect.get("width") or 1280))
    height = max(640, int(rect.get("height") or 820))
    x = rect.get("x")
    y = rect.get("y")
    theme = saved.get("theme") or "light"
    bg_color = "#0A0F18" if theme == "dark" else "#F4F7FB"

    bridge = NativeBridge()
    window = webview.create_window(
        title="抖音下载器",
        url=f"http://127.0.0.1:{port}",
        js_api=bridge,
        width=width,
        height=height,
        x=int(x) if isinstance(x, (int, float)) else None,
        y=int(y) if isinstance(y, (int, float)) else None,
        min_size=(980, 640),
        background_color=bg_color,
        text_select=True,
    )
    bridge.attach_window(window)

    def _on_closing():
        _save_window_geometry(window)

    window.events.closing += _on_closing

    storage_dir = PROJECT_ROOT / "cache" / "webview2"
    storage_dir.mkdir(parents=True, exist_ok=True)
    icon_path = BUNDLED_ROOT / "img" / "app_icon.ico"

    try:
        webview.start(
            gui="edgechromium",
            private_mode=False,
            storage_path=str(storage_dir),
            icon=str(icon_path) if icon_path.exists() else None,
        )
    finally:
        server.should_exit = True
        server_thread.join(timeout=3.0)

    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="DouyinDownloader Desktop")
    parser.add_argument("--self-test", action="store_true", help="Run startup self-test and exit")
    parser.add_argument("--web", action="store_true", help="Serve UI over HTTP without PyWebView")
    parser.add_argument("--port", type=int, default=0, help="Port for --web mode")
    parser.add_argument("--no-open", action="store_true", help="Do not open browser in --web mode")
    args, _ = parser.parse_known_args(argv)

    if args.self_test:
        return _run_self_test()
    if args.web:
        return _run_web_mode(args.port or None, args.no_open)
    return _run_desktop_mode()


if __name__ == "__main__":
    raise SystemExit(main())
