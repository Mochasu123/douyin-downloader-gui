#!/usr/bin/env python3
"""Desktop GUI entry point for Douyin Downloader.

Bootstraps the Tcl/Tk environment, sets up paths, and launches the GUI.
"""

import os
import sys
import traceback
from pathlib import Path


def bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def configure_tcl_tk() -> None:
    root = bundled_root()
    candidates = [
        (root / "_tcl_data", root / "_tk_data"),
        (root / "tcl8.6", root / "tk8.6"),
        (root / "lib" / "tcl8.6", root / "lib" / "tk8.6"),
    ]
    for tcl_dir, tk_dir in candidates:
        if (tcl_dir / "init.tcl").exists():
            os.environ["TCL_LIBRARY"] = str(tcl_dir)
            if tk_dir.exists():
                os.environ["TK_LIBRARY"] = str(tk_dir)
            break


def write_self_test_log(stage: str) -> None:
    if "--self-test" not in sys.argv:
        return
    try:
        log_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        log_path = log_root / "desktop_self_test.log"
        lines = [
            f"stage={stage}",
            f"frozen={getattr(sys, 'frozen', False)}",
            f"executable={sys.executable}",
            f"meipass={getattr(sys, '_MEIPASS', '')}",
            f"bundled_root={bundled_root()}",
            f"TCL_LIBRARY={os.environ.get('TCL_LIBRARY', '')}",
            f"TK_LIBRARY={os.environ.get('TK_LIBRARY', '')}",
            f"tcl_init_exists={Path(os.environ.get('TCL_LIBRARY', '')).joinpath('init.tcl').exists() if os.environ.get('TCL_LIBRARY') else False}",
            f"tk_tcl_exists={Path(os.environ.get('TK_LIBRARY', '')).joinpath('tk.tcl').exists() if os.environ.get('TK_LIBRARY') else False}",
            "",
        ]
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
    except Exception:
        pass


def append_self_test_line(text: str) -> None:
    if "--self-test" not in sys.argv:
        return
    try:
        log_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        with open(log_root / "desktop_self_test.log", "a", encoding="utf-8") as handle:
            handle.write(f"{text}\n")
    except Exception:
        pass


configure_tcl_tk()
write_self_test_log("after_configure_tcl_tk")


def app_root() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent
    exe_dir = Path(sys.executable).resolve().parent
    for path in (exe_dir, *exe_dir.parents):
        if (path / "config.example.yml").exists() or (path / ".git").exists():
            return path
    return exe_dir


PROJECT_ROOT = app_root()
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

APP_DATA = PROJECT_ROOT
APP_DATA.mkdir(parents=True, exist_ok=True)
APP_CONFIG = APP_DATA / "config.yml"
APP_SETTINGS = APP_DATA / "desktop_settings.json"


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import asyncio
        write_self_test_log("before_tk_root")
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.update()
            root.destroy()
            write_self_test_log("after_tk_root")
            append_self_test_line(f"PROJECT_ROOT={PROJECT_ROOT}")
            append_self_test_line(f"APP_CONFIG={APP_CONFIG}")

            from cli.main import main_async, download_url
            from config import ConfigLoader
            from auth import CookieManager
            from core import DouyinAPIClient, DownloaderFactory, URLParser
            from core.discovery import dump_hot_board, search_and_dump
            from core.preview_service import PreviewService
            from storage import Database
            from server.app import run_server

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
            append_self_test_line("core_imports=OK")
            append_self_test_line("sqlite=OK")
            raise SystemExit(0)
        except Exception:
            try:
                log_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
                with open(log_root / "desktop_self_test.log", "a", encoding="utf-8") as handle:
                    handle.write("exception=\n")
                    handle.write(traceback.format_exc())
                    handle.write("\n")
            except Exception:
                pass
            raise SystemExit(1)

    from gui.app import DouyinApp
    app = DouyinApp(PROJECT_ROOT, APP_CONFIG, APP_SETTINGS)
    app.mainloop()
