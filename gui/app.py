"""Main GUI application window — collapsible side log panel + tab memory."""

from __future__ import annotations

import json
import queue
import webbrowser
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, messagebox, ttk
import tkinter as tk

from gui.controller import (
    AppController, classify_error, default_download_dir, human_size,
    mode_label, mode_value,
)
from gui.theme import apply_theme, TEXT_DARK
from gui.widgets.settings_tab import SettingsTab
from gui.widgets.link_tab import LinkTab
from gui.widgets.progress import ProgressPanel
from gui.widgets.log_tab import LogTab
from gui.widgets.history_tab import HistoryTab


LOG_PANEL_WIDTH = 300
LOG_BTN_WIDTH = 28


class DouyinApp(tk.Tk):
    def __init__(self, project_root: Path, app_config: Path, app_settings: Path):
        super().__init__()
        self.title("抖音下载器")
        self.geometry("1100x780")
        self.minsize(860, 560)

        self.project_root = project_root
        self.app_config = app_config
        self.app_settings = app_settings
        self._log_expanded = False

        apply_theme(self)

        self.ctrl = AppController(project_root, app_config, app_settings, self._log)
        self.ctrl.set_busy_callback(self._set_busy_buttons)

        self._init_variables()
        self._build_ui()
        self._restore_window_geometry()
        self._restore_last_tab()

        self._completion_stats: dict = {}
        self.after(100, self._drain_output)
        self.after(500, self._check_first_launch)

    # ══════════════════════════════════════════════════════════════

    def _init_variables(self):
        cfg = self.ctrl.config_data
        self.path_var = StringVar(value=cfg.get("path") or default_download_dir())
        self.retry_var = IntVar(value=int(cfg.get("retry_times") or 3))
        self.cover_var = BooleanVar(value=bool(cfg.get("cover", True)))
        self.music_var = BooleanVar(value=bool(cfg.get("music", False)))
        self.avatar_var = BooleanVar(value=bool(cfg.get("avatar", True)))
        self.json_var = BooleanVar(value=bool(cfg.get("json", True)))
        self.increase_var = BooleanVar(
            value=bool((cfg.get("increase") or {}).get("post", False)))
        self.browser_fallback_var = BooleanVar(
            value=bool((cfg.get("browser_fallback") or {}).get("enabled", True)))

        self.cookie_var = StringVar(value="")
        self._load_saved_cookie()

        self.urls_var = StringVar(value="\n".join(cfg.get("link", []) or []))
        self.limit_var = IntVar(value=int((cfg.get("number") or {}).get("post") or 0))

        self.total_progress_var = DoubleVar(value=0)
        self.file_progress_var = DoubleVar(value=0)
        self.status_var = StringVar(value="空闲")
        self.file_status_var = StringVar(value="当前文件：无")

    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Main area (left) ─────────────────────────────────────
        main = ttk.Frame(self)
        main.grid(row=0, column=0, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(8, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Tab 1: Settings
        self.settings_tab = SettingsTab(
            self.notebook, self.path_var, self.cookie_var, self.retry_var,
            self.browser_fallback_var,
            on_save=self._on_save, on_open_dir=self._on_open_dir,
            on_clear_log=self._on_clear_log,
        )
        self.notebook.add(self.settings_tab, text="⚙️ 设置")

        # Tab 2: Link download
        self.link_tab = LinkTab(
            self.notebook, self.urls_var, self.limit_var,
            self.cover_var, self.music_var, self.avatar_var, self.json_var,
            self.increase_var,
            on_preview=self._on_link_preview, on_start=self._on_link_start,
            on_pause=self._on_pause, on_resume=self._on_resume, on_stop=self._on_stop,
        )
        self.notebook.add(self.link_tab, text="🔗 链接下载")

        # Tab 3: History
        db_path = str(self.project_root / "dy_downloader.db")
        self.history_tab = HistoryTab(self.notebook, db_path)
        self.notebook.add(self.history_tab, text="📋 下载记录")

        # Progress bar (inside main)
        self.progress = ProgressPanel(
            main, self.total_progress_var, self.file_progress_var,
            self.status_var, self.file_status_var,
        )
        self.progress.grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(4, 8))

        # ── Side log panel (right) ───────────────────────────────
        self._build_log_panel()

    def _build_log_panel(self):
        panel = ttk.Frame(self)
        panel.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=(8, 8))
        panel.grid_propagate(False)
        panel.configure(width=LOG_BTN_WIDTH)

        # Collapsed state: just a vertical toggle button
        self.log_toggle_btn = tk.Button(panel, text="日\n志", relief="flat", bd=0,
                                         bg="#E8E8E8", fg="#666",
                                         font=("Microsoft YaHei UI", 9),
                                         cursor="hand2", padx=3, pady=8,
                                         command=self._toggle_log_panel)
        self.log_toggle_btn.pack(fill="both", expand=True)

        # Expanded content (hidden initially)
        self._log_expanded_frame = ttk.Frame(panel)
        hdr = ttk.Frame(self._log_expanded_frame)
        hdr.pack(fill="x")
        tk.Button(hdr, text="◀ 收起", relief="flat", bd=0, bg="#EEEEEE", fg=TEXT_DARK,
                  font=("Microsoft YaHei UI", 8), cursor="hand2",
                  anchor="w", padx=8, pady=2,
                  command=self._toggle_log_panel).pack(side="left", fill="x", expand=True)
        tk.Button(hdr, text="✕ 清空", relief="flat", bd=0, bg="#EEEEEE", fg="#999",
                  font=("Microsoft YaHei UI", 8), cursor="hand2",
                  command=self._on_clear_log).pack(side="right", padx=(0, 2))

        log_frame = ttk.Frame(self._log_expanded_frame)
        log_frame.pack(fill="both", expand=True)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_tab = LogTab(log_frame)
        self.log_tab.grid(row=0, column=0, sticky="nsew")

        self.log_panel = panel

    def _toggle_log_panel(self):
        if self._log_expanded:
            self._log_expanded_frame.pack_forget()
            self.log_toggle_btn.pack(fill="both", expand=True)
            self.log_panel.configure(width=LOG_BTN_WIDTH)
            self.log_toggle_btn.configure(text="日\n志")
            self._log_expanded = False
        else:
            self.log_toggle_btn.pack_forget()
            self._log_expanded_frame.pack(fill="both", expand=True)
            self.log_panel.configure(width=LOG_PANEL_WIDTH)
            self._log_expanded = True

    # ══════════════════════════════════════════════════════════════
    # Tab switching + memory
    # ══════════════════════════════════════════════════════════════

    def _on_tab_changed(self, event):
        tab = self.notebook.tab(self.notebook.select(), "text")
        if tab == "📋 下载记录":
            self.history_tab.load_page()
        self._save_last_tab()

    def _save_last_tab(self):
        try:
            idx = self.notebook.index(self.notebook.select())
            data = {}
            if self.app_settings.exists():
                data = json.loads(self.app_settings.read_text(encoding="utf-8"))
            data["last_tab"] = idx
            data["window_geometry"] = self.geometry()
            self.app_settings.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        except Exception:
            pass

    def _restore_last_tab(self):
        try:
            if not self.app_settings.exists():
                return
            data = json.loads(self.app_settings.read_text(encoding="utf-8"))
            idx = data.get("last_tab", None)
            # If cookies exist, default to link tab (index 1), otherwise settings (index 0)
            if idx is None:
                cookie_file = self.project_root / ".cookies.json"
                idx = 1 if (cookie_file.exists() and
                            json.loads(cookie_file.read_text(encoding="utf-8"))) else 0
            self.notebook.select(max(0, min(idx, len(self.notebook.tabs()) - 1)))
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════
    # (rest unchanged — actions, drain loop, etc.)
    # ══════════════════════════════════════════════════════════════

    def _collect_form_values(self) -> dict:
        return {
            "links": self.link_tab.get_urls(),
            "path": self.path_var.get(),
            "cookie": self.settings_tab.get_cookie(),
            "modes": self.link_tab.get_selected_modes(),
            "limit": self.limit_var.get(),
            "retry": self.retry_var.get(),
            "cover": self.cover_var.get(),
            "music": self.music_var.get(),
            "avatar": self.avatar_var.get(),
            "json": self.json_var.get(),
            "increase": self.increase_var.get(),
            "browser_fallback": self.browser_fallback_var.get(),
        }

    def _on_save(self):
        try:
            self.ctrl.save_config(self._collect_form_values())
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))

    def _on_open_dir(self):
        path = Path(self.path_var.get() or default_download_dir())
        path.mkdir(parents=True, exist_ok=True)
        webbrowser.open(path.as_uri())

    def _on_clear_log(self):
        self.log_tab.clear()

    def _on_pause(self):
        self.ctrl.pause()
        self.status_var.set("已暂停")
        self._log("已请求暂停。\n")

    def _on_resume(self):
        self.ctrl.resume()
        self.status_var.set("继续下载")
        self._log("已继续。\n")

    def _on_stop(self):
        self.ctrl.stop()
        self.status_var.set("正在终止")
        self._log("已请求终止。\n")

    def _log(self, text: str):
        self.log_tab.append(text)

    def _set_busy_buttons(self, busy: bool):
        self.link_tab.set_busy(busy)

    def _on_link_preview(self):
        if self.ctrl.worker and self.ctrl.worker.is_alive():
            return
        form = self._collect_form_values()
        if not form["links"]:
            return
        try:
            self.ctrl.save_config(form)
        except Exception:
            pass
        if not form["cookie"]:
            self._log("提示：Cookie 为空，可能无法获取作品信息。\n")
        self.link_tab.preview.clear()
        self.total_progress_var.set(0)
        self.status_var.set("解析中")
        self.file_status_var.set("当前文件：无")
        self._set_busy_buttons(True)
        mode = (form["modes"] or ["post"])[0]
        try:
            self.ctrl.start_preview(form, mode)
        except Exception as exc:
            messagebox.showerror("错误", classify_error(exc))
            self._set_busy_buttons(False)

    def _on_link_start(self):
        if self.ctrl.worker and self.ctrl.worker.is_alive():
            messagebox.showinfo("正在下载", "当前任务还在运行。")
            return
        form = self._collect_form_values()
        if not form["links"]:
            messagebox.showwarning("缺少链接", "请至少输入一个抖音链接。")
            return
        if not form["cookie"]:
            if not messagebox.askyesno("Cookie 为空", "没有 Cookie 也许会失败，仍然继续吗？"):
                return
        Path(form["path"]).mkdir(parents=True, exist_ok=True)
        self.total_progress_var.set(0)
        self.status_var.set("开始下载")
        self.file_status_var.set("当前文件：无")
        self._set_busy_buttons(True)
        selected = self._selected_items(self.link_tab.preview)
        self.ctrl.start_download(form, selected)

    def _selected_items(self, preview) -> list:
        selected_iids = preview.get_selected_iids()
        if not selected_iids:
            return list(self.ctrl.preview_items)
        return [
            self.ctrl.preview_item_by_iid[iid]
            for iid in selected_iids
            if iid in self.ctrl.preview_item_by_iid
        ]

    def _restore_window_geometry(self):
        try:
            if not self.app_settings.exists():
                return
            settings = json.loads(self.app_settings.read_text(encoding="utf-8"))
            geom = settings.get("window_geometry")
            if geom:
                self.geometry(geom)
        except Exception:
            pass

    def _load_saved_cookie(self):
        cookie_json = self.project_root / ".cookies.json"
        cookie_str = ""
        try:
            if cookie_json.exists():
                data = json.loads(cookie_json.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data:
                    cookie_str = "; ".join(f"{k}={v}" for k, v in data.items())
        except Exception:
            pass
        if not cookie_str:
            cookie_str = (self.ctrl.config_data.get("cookie") or "").strip()
        self.cookie_var.set(cookie_str)

    def _check_first_launch(self):
        config_path = self.project_root / "config.yml"
        if config_path.exists():
            return
        self._show_welcome_wizard()

    def _show_welcome_wizard(self):
        wizard = tk.Toplevel(self)
        wizard.title("欢迎使用抖音下载器")
        wizard.geometry("520x440")
        wizard.resizable(False, False)
        wizard.transient(self)
        wizard.grab_set()

        pages: list[ttk.Frame] = []
        current_page = [0]

        def _show_page(idx):
            for p in pages:
                p.grid_remove()
            pages[idx].grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 16))
            prev_btn.configure(state="normal" if idx > 0 else "disabled")
            next_btn.configure(text="完成！" if idx == len(pages) - 1 else "下一步 →")

        def _next():
            if current_page[0] < len(pages) - 1:
                current_page[0] += 1
                _show_page(current_page[0])
            else:
                wizard.destroy()

        def _prev():
            if current_page[0] > 0:
                current_page[0] -= 1
                _show_page(current_page[0])

        wizard.columnconfigure(0, weight=1)
        wizard.rowconfigure(0, weight=0)
        wizard.rowconfigure(1, weight=1)

        hdr = ttk.Frame(wizard, padding=(20, 16))
        hdr.grid(row=0, column=0, sticky="ew")
        ttk.Label(hdr, text="🎬 抖音下载器", font=("Microsoft YaHei UI", 16, "bold"),
                  foreground="#FE2C55").pack(anchor="center")

        p0 = ttk.Frame(wizard, padding=10)
        ttk.Label(p0, text="欢迎使用抖音无水印批量下载工具！",
                  font=("Microsoft YaHei UI", 12, "bold")).pack(pady=(20, 0))
        ttk.Label(p0, text="本工具可以帮助你：\n\n"
                  "• 批量下载抖音视频（无水印）\n• 按合集组织下载\n"
                  "• 下载用户主页全部作品\n• 图集、封面、头像等资源\n\n"
                  "首先需要设置下载目录和 Cookie。",
                  font=("Microsoft YaHei UI", 10), wraplength=440,
                  justify="left").pack(pady=(16, 0))
        pages.append(p0)

        p1 = ttk.Frame(wizard, padding=10)
        ttk.Label(p1, text="设置下载目录",
                  font=("Microsoft YaHei UI", 12, "bold")).pack(pady=(20, 0))
        ttk.Label(p1, text="选择下载文件保存的位置：",
                  font=("Microsoft YaHei UI", 10)).pack(pady=(16, 6))
        dir_entry = ttk.Entry(p1)
        dir_entry.pack(fill="x")
        dir_entry.insert(0, default_download_dir())
        pages.append(p1)

        p2 = ttk.Frame(wizard, padding=10)
        ttk.Label(p2, text="准备好了！",
                  font=("Microsoft YaHei UI", 12, "bold")).pack(pady=(20, 0))
        ttk.Label(p2, text="操作指南：\n\n"
                  "1️⃣  在「⚙️ 设置」标签页粘贴 Cookie（浏览器 F12 获取）\n"
                  "2️⃣  在「🔗 链接下载」粘贴抖音链接，自动预览\n"
                  "3️⃣  按合集筛选 → 勾选作品 → 点击「开始下载」\n\n"
                  "下载完成后右下角会弹出通知！",
                  font=("Microsoft YaHei UI", 10), wraplength=440,
                  justify="left").pack(pady=(16, 0))
        pages.append(p2)

        nav = ttk.Frame(wizard, padding=(20, 0, 20, 16))
        nav.grid(row=2, column=0, sticky="ew")
        prev_btn = ttk.Button(nav, text="← 上一步", command=_prev, state="disabled")
        prev_btn.pack(side="left")
        next_btn = ttk.Button(nav, text="下一步 →", command=_next, style="Primary.TButton")
        next_btn.pack(side="right")

        _show_page(0)
        wizard.wait_window()
        self.path_var.set(dir_entry.get())
        try:
            self.ctrl.save_config(self._collect_form_values())
        except Exception:
            pass

    def _show_completion_notification(self, success: int, failed: int, skipped: int):
        total = success + failed + skipped
        if total == 0:
            return
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.configure(bg="#2E7D32" if failed == 0 else "#E65100")
        msg = f"任务完成 — 共 {total} 项，成功 {success}"
        if failed:
            msg += f"，失败 {failed}"
        if skipped:
            msg += f"，跳过 {skipped}"
        tk.Label(toast, text=msg, bg=toast.cget("bg"), fg="white",
                 font=("Microsoft YaHei UI", 10), padx=20, pady=12).pack()
        toast.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        tw = toast.winfo_width()
        th = toast.winfo_height()
        toast.geometry(f"+{sw - tw - 30}+{sh - th - 60}")
        self.after(4000, toast.destroy)

    # ══════════════════════════════════════════════════════════════
    # Output drain loop
    # ══════════════════════════════════════════════════════════════

    def _drain_output(self):
        try:
            while True:
                item = self.ctrl.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self._set_busy_buttons(False)
                    if self.ctrl.cancel_event.is_set():
                        self.status_var.set("已终止")
                    elif self.status_var.get() not in {"解析完成", "任务完成"}:
                        self.status_var.set("空闲")
                        stats = self._completion_stats
                        if stats.get("completed", 0) > 0:
                            self._show_completion_notification(
                                int(stats.get("success", 0)),
                                int(stats.get("failed", 0)),
                                int(stats.get("skipped", 0)),
                            )
                        self._completion_stats = {}
                elif isinstance(item, tuple) and item[0] == "__STATUS__":
                    self.status_var.set(str(item[1]))
                    self._log(str(item[1]) + "\n")
                elif isinstance(item, tuple) and item[0] == "__LOG__":
                    self._log(str(item[1]))
                elif isinstance(item, tuple) and item[0] == "__PREVIEW_ITEM__":
                    self.ctrl.preview_items.append(item[1])
                    iid = f"row_{len(self.ctrl.preview_items)}"
                    self.ctrl.preview_item_by_iid[iid] = item[1]
                    self.link_tab.preview.add_item(item[1], len(self.ctrl.preview_items))
                elif isinstance(item, tuple) and item[0] == "__PREVIEW_DONE__":
                    count = int(item[1] or 0)
                    self.status_var.set("解析完成")
                    self.total_progress_var.set(0)
                    self._log(f"完成，共 {count} 个作品。\n")
                    collections: list[str] = []
                    seen: set[str] = set()
                    for p in self.ctrl.preview_items:
                        c = getattr(p, "collection_name", "") or ""
                        if c and c not in seen:
                            seen.add(c)
                            collections.append(c)
                    self.link_tab.preview.set_collections(collections)
                    items = self.ctrl.preview_items
                    if items:
                        source = getattr(items[0], "source_type", "")
                        is_single = source in ("video", "gallery", "music", "live", "collection")
                        self.link_tab.set_limit_disabled(is_single)
                        if is_single:
                            self.limit_var.set(0)
                    self.link_tab.update_download_count()
                    self.link_tab.preview.tree.bind("<<TreeviewSelect>>",
                                                     lambda _: self.link_tab.update_download_count())
                elif isinstance(item, tuple) and item[0] == "__ROW_STATUS_BY_ID__":
                    _, aweme_id, status, size_text = item
                    self.link_tab.preview.update_status(str(aweme_id), str(status), size_text)
                elif isinstance(item, tuple) and item[0] == "__TOTAL_PROGRESS__":
                    _, completed, total, success, failed, skipped = item
                    self._completion_stats = {
                        "success": success, "failed": failed, "skipped": skipped,
                        "completed": completed, "total": total,
                    }
                    percent = (int(completed) / int(total) * 100) if int(total or 0) else 0
                    self.total_progress_var.set(percent)
                    self.status_var.set(
                        f"总进度 {completed}/{total}，成功 {success}，失败 {failed}，跳过 {skipped}")
                elif isinstance(item, tuple) and item[0] == "__FILE_PROGRESS__":
                    _, file_name, written, expected = item
                    if expected:
                        self.file_progress_var.set(min(100, int(written) / int(expected) * 100))
                        self.file_status_var.set(
                            f"{file_name}：{human_size(int(written))}/{human_size(int(expected))}")
                    else:
                        self.file_progress_var.set(0)
                        self.file_status_var.set(f"{file_name}：{human_size(int(written))}")
                elif isinstance(item, str):
                    self._log(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_output)
