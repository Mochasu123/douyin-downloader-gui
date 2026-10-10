"""Main GUI application window — collapsible side log panel + tab memory."""

from __future__ import annotations

import json
import os
import queue
from pathlib import Path
from tkinter import BooleanVar, DoubleVar, IntVar, StringVar, messagebox, ttk
import tkinter as tk

from gui.controller import (
    AppController, classify_error, default_download_dir, human_size,
    mode_label, mode_value, url_type_label, video_quality_label,
)
from gui.theme import apply_theme, BG, BLUE, FONT, FONT_SECTION, FONT_SMALL, FONT_TITLE
from gui.widgets.gradient_header import GradientHeader
from gui.widgets.rounded_button import RoundedButton
from gui.widgets.settings_tab import SettingsTab
from gui.widgets.link_tab import LinkTab
from gui.widgets.comments_tab import CommentsTab
from gui.widgets.user_tab import UserTab
from gui.widgets.progress import ProgressPanel
from gui.widgets.log_tab import LogTab
from gui.widgets.history_tab import HistoryTab


LOG_PANEL_WIDTH = 300


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

        import sv_ttk
        sv_ttk.set_theme("light")
        apply_theme(self)
        self._set_app_icon()

        self.ctrl = AppController(project_root, app_config, app_settings, self._log)
        self.ctrl.set_busy_callback(self._set_busy_buttons)
        self.ctrl.set_user_busy_callback(self._set_user_busy_buttons)

        self._init_variables()
        self._saved_cookie_value = self.cookie_var.get()
        self._build_ui()
        self._restore_window_geometry()
        self._select_default_tab()

        self._completion_stats: dict = {}
        self._unsupported_labels: set = set()
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
        self.homepage_screenshot_var = BooleanVar(
            value=bool(cfg.get("homepage_screenshot", False)))
        self.live_photo_merge_var = BooleanVar(
            value=bool(cfg.get("live_photo_merge", True)))
        self.video_quality_var = StringVar(
            value=video_quality_label(cfg.get("video_quality")))
        self.browser_fallback_var = BooleanVar(
            value=bool((cfg.get("browser_fallback") or {}).get("enabled", True)))

        self.cookie_var = StringVar(value="")
        self._load_saved_cookie()

        self.urls_var = StringVar(value="\n".join(cfg.get("link", []) or []))
        self.limit_var = IntVar(value=int((cfg.get("number") or {}).get("post") or 0))

        self.total_progress_var = DoubleVar(value=0)
        self.file_progress_var = DoubleVar(value=0)
        self.status_var = StringVar(value="空闲")
        self.file_status_var = StringVar(value="")

    # ══════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Top bar: gradient banner + log toggle (entry point) ──
        top_bar = ttk.Frame(self)
        top_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        top_bar.columnconfigure(0, weight=1)

        header = GradientHeader(top_bar, title="抖音下载器",
                                subtitle="抖音无水印批量下载工具 · 蓝白主题")
        header.grid(row=0, column=0, sticky="nsew")

        self.log_btn = RoundedButton(top_bar, text="📋 日志", style="ghost",
                                     height=30, command=self._toggle_log_panel)
        self.log_btn.grid(row=0, column=1, sticky="e", padx=(0, 16), pady=15)

        # ── Main area (left) ─────────────────────────────────────
        main = ttk.Frame(self)
        main.grid(row=1, column=0, sticky="nsew")
        main.rowconfigure(0, weight=1)
        main.columnconfigure(0, weight=1)

        self.notebook = ttk.Notebook(main)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=(8, 0))
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Tab 1: Link download
        self.link_tab = LinkTab(
            self.notebook, self.urls_var,
            on_preview=self._on_link_preview, on_start=self._on_link_start,
            on_pause=self._on_pause, on_resume=self._on_resume, on_stop=self._on_stop,
            on_history=self._on_link_history,
        )
        self.notebook.add(self.link_tab, text="🔗 链接下载")

        # Tab 2: User homepage (sub-mode operations)
        self.user_tab = UserTab(
            self.notebook,
            on_load=self._on_user_load,
            on_start=self._on_user_start,
            on_pause=self._on_pause,
            on_resume=self._on_resume,
            on_stop=self._on_stop,
            on_history=self._on_user_history,
        )
        self.notebook.add(self.user_tab, text="👤 用户主页")

        # Tab 3: Comments (enabled only for a single video/gallery preview)
        self.comments_tab = CommentsTab(
            self.notebook,
            on_load=lambda: self.ctrl.start_comments_load(
                self.comments_tab.get_aweme_id()),
            on_download=lambda images, save_dir: (
                self.ctrl.start_comment_image_download(images, save_dir)),
            on_zoom=lambda key, cid, idx: (
                self.ctrl.start_comment_zoom(key, cid, idx)),
            on_open_dir=self._on_open_comments_dir,
        )
        self.notebook.add(self.comments_tab, text="💬 评论")
        self.notebook.tab(self.comments_tab, state="disabled")

        # Tab 4: History
        db_path = str(self.project_root / "dy_downloader.db")
        self.history_tab = HistoryTab(self.notebook, db_path)
        self.notebook.add(self.history_tab, text="📋 下载记录")

        # Tab 5: Settings (last, after configuration is done)
        self.settings_tab = SettingsTab(
            self.notebook, self.path_var, self.cookie_var, self.retry_var,
            self.browser_fallback_var, self.video_quality_var,
            self.cover_var, self.music_var, self.avatar_var, self.json_var,
            self.increase_var, self.homepage_screenshot_var,
            self.live_photo_merge_var,
            on_save=self._on_save, on_open_dir=self._on_open_dir,
        )
        self.notebook.add(self.settings_tab, text="⚙️ 设置")

        # Progress bar (inside main)
        self.progress = ProgressPanel(
            main, self.total_progress_var, self.file_progress_var,
            self.status_var, self.file_status_var,
        )
        self.progress.grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=(4, 8))

        # ── Side log panel (right) ───────────────────────────────
        self._build_log_panel()

    def _build_log_panel(self):
        panel = ttk.Frame(self, style="LogPanel.TFrame")
        panel.grid_propagate(False)
        panel.configure(width=LOG_PANEL_WIDTH)

        hdr = ttk.Frame(panel, style="LogPanel.TFrame")
        hdr.pack(fill="x")
        RoundedButton(hdr, text="◀ 收起", style="ghost", height=28,
                      command=self._toggle_log_panel
                      ).pack(side="left", fill="x", expand=True)
        RoundedButton(hdr, text="✕ 清空", style="ghost", height=28,
                      command=self._on_clear_log).pack(side="right", padx=(0, 2))

        log_frame = ttk.Frame(panel)
        log_frame.pack(fill="both", expand=True)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_tab = LogTab(log_frame)
        self.log_tab.grid(row=0, column=0, sticky="nsew")

        self.log_panel = panel
        # The panel stays hidden until the top-bar toggle is clicked;
        # _toggle_log_panel() shows it with grid(row=1, column=1).

    def _toggle_log_panel(self):
        if self._log_expanded:
            self.log_panel.grid_remove()
            self.log_btn.set_text("📋 日志")
            self.log_btn.configure(style="ghost")
            self._log_expanded = False
        else:
            self.log_panel.grid(row=1, column=1, sticky="ns",
                                padx=(0, 8), pady=(0, 10))
            self.log_btn.set_text("📋 收起日志")
            self.log_btn.configure(style="primary")
            self._log_expanded = True

    # ══════════════════════════════════════════════════════════════
    # Tab switching + memory
    # ══════════════════════════════════════════════════════════════

    def _on_tab_changed(self, event):
        tab = self.notebook.tab(self.notebook.select(), "text")
        if tab == "📋 下载记录":
            self.history_tab.load_page()
        if tab == "💬 评论":
            self.comments_tab.refresh_view()
        self._save_window_geometry()

    def _save_window_geometry(self):
        try:
            data = {}
            if self.app_settings.exists():
                data = json.loads(self.app_settings.read_text(encoding="utf-8"))
            data["window_geometry"] = self.geometry()
            self.app_settings.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        except Exception:
            pass

    def _select_default_tab(self):
        """已配置时默认进入第一个页签（链接下载）；未配置时进入设置页。"""
        try:
            configured = bool(self.cookie_var.get().strip())
            if configured:
                self.notebook.select(self.link_tab)
                self.status_var.set("已配置，可直接使用")
                self._log("Cookie 已配置，可直接开始下载。\n")
            else:
                self.notebook.select(self.settings_tab)
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
            "homepage_screenshot": self.homepage_screenshot_var.get(),
            "live_photo_merge": self.live_photo_merge_var.get(),
            "video_quality": self.video_quality_var.get(),
            "browser_fallback": self.browser_fallback_var.get(),
        }

    def _on_save(self):
        try:
            self.ctrl.save_config(self._collect_form_values())
            cookie = self.cookie_var.get().strip()
            cookie_changed = cookie != self._saved_cookie_value
            self._saved_cookie_value = cookie
            if cookie and cookie_changed:
                self._log("Cookie 已保存并生效。\n")
                messagebox.showinfo(
                    "配置完成",
                    "Cookie 已配置成功。重启应用后将默认进入「链接下载」页，"
                    "不再停留在设置页。")
            return True
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return False

    def _on_open_dir(self):
        # Windows-native: open the folder straight in Explorer (os.startfile
        # is Windows-only, which is fine — this app targets Windows).
        path = Path(self.path_var.get() or default_download_dir())
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path))

    def _on_open_comments_dir(self):
        path = (self.comments_tab.get_save_dir()
                or self.path_var.get() or default_download_dir())
        Path(path).mkdir(parents=True, exist_ok=True)
        os.startfile(path)

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

    def _set_user_busy_buttons(self, busy: bool):
        self.user_tab.set_busy(busy)

    def _on_link_preview(self):
        if self.ctrl.worker and self.ctrl.worker.is_alive():
            return
        self._unsupported_labels.clear()
        self.link_tab.set_type_label("")
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
        self.comments_tab.reset()
        self.notebook.tab(self.comments_tab, state="disabled")
        self.total_progress_var.set(0)
        self.status_var.set("解析中")
        self.file_status_var.set("")
        self.file_progress_var.set(0)
        self.progress.set_progress_visible(False)
        self._set_busy_buttons(True)
        mode = (form["modes"] or ["post"])[0]
        try:
            self.ctrl.start_preview(form, mode)
        except Exception as exc:
            messagebox.showerror("错误", classify_error(exc))
            self._set_busy_buttons(False)

    def _on_user_load(self):
        if self.ctrl.user_worker and self.ctrl.user_worker.is_alive():
            return
        sec_uid = self.user_tab.get_sec_uid()
        if not sec_uid:
            messagebox.showwarning(
                "缺少链接", "请粘贴用户主页链接，例如 https://www.douyin.com/user/xxxx")
            return
        form = self._collect_form_values()
        form["modes"] = [self.user_tab.get_selected_mode()]
        form["limit"] = self.user_tab.get_limit()
        form["increase"] = self.user_tab.get_increase()
        form["links"] = [self.user_tab.get_url()]
        form["sec_uid"] = sec_uid
        try:
            self.ctrl.save_config(form)
        except Exception:
            pass
        self.user_tab.reset()
        self.user_tab.set_busy(True)
        self.total_progress_var.set(0)
        self.file_status_var.set("")
        self.file_progress_var.set(0)
        self.progress.set_progress_visible(False)
        self.status_var.set("加载用户作品中")
        try:
            self.ctrl.start_user_preview(form)
        except Exception as exc:
            messagebox.showerror("错误", classify_error(exc))
            self.user_tab.set_busy(False)

    def _on_user_start(self):
        if self.ctrl.user_worker and self.ctrl.user_worker.is_alive():
            messagebox.showinfo("正在下载", "当前任务还在运行。")
            return
        if not self.user_tab.get_sec_uid():
            messagebox.showwarning("缺少链接", "请先粘贴用户主页链接并加载作品。")
            return
        form = self._collect_form_values()
        form["modes"] = [self.user_tab.get_selected_mode()]
        form["limit"] = self.user_tab.get_limit()
        form["increase"] = self.user_tab.get_increase()
        form["links"] = [self.user_tab.get_url()]
        form["sec_uid"] = self.user_tab.get_sec_uid()
        selected = self._selected_items(self.user_tab.preview)
        self.user_tab.set_busy(True)
        self.status_var.set("开始下载")
        self.file_status_var.set("当前文件：无")
        self.file_progress_var.set(0)
        self.progress.set_progress_visible(True)
        self.ctrl.start_user_download(form, selected)

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
        self.progress.set_progress_visible(True)
        self._set_busy_buttons(True)
        selected = self._selected_items(self.link_tab.preview)
        self.ctrl.start_download(form, selected)

    # ── 历史链接 / 历史用户 ─────────────────────────────────────────

    def _on_link_history(self):
        from gui.widgets.history_dialog import LinkHistoryDialog

        rows = self.ctrl.fetch_link_history()
        dialog = LinkHistoryDialog(
            self, rows,
            on_pick=lambda url: self._use_link_history(dialog, url),
            fetch_rows=self.ctrl.fetch_link_history,
            on_delete=self.ctrl.delete_history_entries,
            on_clear=lambda: self.ctrl.clear_history_kinds(
                ["video", "gallery", "collection", "music"]),
        )

    def _use_link_history(self, dialog, url: str):
        text = self.link_tab.urls_text
        existing = text.get("1.0", "end").strip()
        if existing:
            text.insert("end", "\n" + url)
        else:
            text.insert("1.0", url)
        dialog.destroy()

    def _on_user_history(self):
        from gui.widgets.history_dialog import UserHistoryDialog

        rows = self.ctrl.fetch_user_history()
        dialog = UserHistoryDialog(
            self, rows,
            avatar_dir=str(self.project_root / "cache" / "avatars"),
            on_pick=lambda url: self._use_user_history(dialog, url),
            fetch_rows=self.ctrl.fetch_user_history,
            on_delete=self.ctrl.delete_history_entries,
            on_clear=lambda: self.ctrl.clear_history_kinds(["user"]),
        )

    def _use_user_history(self, dialog, url: str):
        self.user_tab.set_url(url)
        dialog.destroy()

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

    def _set_app_icon(self):
        ico = self.project_root / "img" / "app_icon.ico"
        try:
            if ico.exists():
                self.iconbitmap(str(ico))
                return
        except Exception:
            pass
        png = self.project_root / "img" / "logo.png"
        if png.exists():
            try:
                from PIL import ImageTk

                photo = ImageTk.PhotoImage(file=str(png))
                self._app_icon_photo = photo
                self.iconphoto(True, photo)
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
        wizard.configure(bg=BG)

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
        ttk.Label(hdr, text="🎬 抖音下载器", font=FONT_TITLE,
                  foreground=BLUE).pack(anchor="center")

        p0 = ttk.Frame(wizard, padding=10)
        ttk.Label(p0, text="欢迎使用抖音无水印批量下载工具！",
                  font=FONT_SECTION).pack(pady=(20, 0))
        ttk.Label(p0, text="本工具可以帮助你：\n\n"
                  "• 批量下载抖音视频（无水印）\n• 按合集组织下载\n"
                  "• 下载用户主页全部作品\n• 图集、封面、头像等资源\n\n"
                  "首先需要设置下载目录和 Cookie。",
                  font=FONT, wraplength=440,
                  justify="left").pack(pady=(16, 0))
        pages.append(p0)

        p1 = ttk.Frame(wizard, padding=10)
        ttk.Label(p1, text="设置下载目录",
                  font=FONT_SECTION).pack(pady=(20, 0))
        ttk.Label(p1, text="选择下载文件保存的位置：",
                  font=FONT).pack(pady=(16, 6))
        dir_entry = ttk.Entry(p1)
        dir_entry.pack(fill="x")
        dir_entry.insert(0, default_download_dir())
        pages.append(p1)

        p2 = ttk.Frame(wizard, padding=10)
        ttk.Label(p2, text="准备好了！",
                  font=FONT_SECTION).pack(pady=(20, 0))
        ttk.Label(p2, text="操作指南：\n\n"
                  "1️⃣  在「⚙️ 设置」标签页粘贴 Cookie（浏览器 F12 获取）\n"
                  "2️⃣  在「🔗 链接下载」粘贴抖音链接，自动预览\n"
                  "3️⃣  按合集筛选 → 勾选作品 → 点击「开始下载」\n\n"
                  "下载完成后右下角会弹出通知！",
                  font=FONT, wraplength=440,
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
        ok = failed == 0
        accent = BLUE if ok else "#EF4444"
        toast.configure(bg="#FFFFFF")
        tk.Frame(toast, bg=accent, height=4).pack(fill="x")
        msg = f"任务完成 — 共 {total} 项，成功 {success}"
        if failed:
            msg += f"，失败 {failed}"
        if skipped:
            msg += f"，跳过 {skipped}"
        tk.Label(toast, text=msg, bg="#FFFFFF", fg=accent,
                 font=("Microsoft YaHei UI", 11, "bold"), padx=26, pady=16).pack()
        toast.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        tw = toast.winfo_width()
        th = toast.winfo_height()
        base_y = sh - th - 60
        toast.geometry(f"+{sw - tw - 30}+{base_y + 24}")
        toast.attributes("-alpha", 0.0)

        # fade in + slide up
        def _fade_in(step):
            if step >= 10:
                toast.attributes("-alpha", 1.0)
                toast.geometry(f"+{sw - tw - 30}+{base_y}")
                self.after(3200, _fade_out)
                return
            toast.attributes("-alpha", step / 10)
            y = base_y + int(24 * (1 - step / 10))
            toast.geometry(f"+{sw - tw - 30}+{y}")
            self.after(22, lambda: _fade_in(step + 1))

        # fade out before destroying
        def _fade_out():
            def _hide(step):
                if step <= 0:
                    toast.destroy()
                    return
                toast.attributes("-alpha", step / 10)
                self.after(20, lambda: _hide(step - 1))
            _hide(10)

        _fade_in(0)

    # ══════════════════════════════════════════════════════════════
    # Output drain loop
    # ══════════════════════════════════════════════════════════════

    def _drain_output(self):
        try:
            while True:
                item = self.ctrl.output_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "__DONE__":
                    self._set_busy_buttons(False)
                    self._set_user_busy_buttons(False)
                    self.progress.set_progress_visible(False)
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
                elif isinstance(item, tuple) and item[0] == "__URL_TYPE__":
                    self.link_tab.set_type_label(str(item[1]))
                elif isinstance(item, tuple) and item[0] == "__LIVE_UNSUPPORTED__":
                    self._unsupported_labels.add(str(item[1]))
                elif isinstance(item, tuple) and item[0] == "__USER_URL__":
                    _, sec_uid = item
                    self.user_tab.set_url(f"https://www.douyin.com/user/{sec_uid}")
                    self.notebook.select(self.user_tab)
                    self._log(f"用户主页链接已转入「用户主页」页签（{sec_uid}）\n")
                    self.status_var.set("请在「用户主页」页签选择下载内容并加载作品")
                elif isinstance(item, tuple) and item[0] == "__USER_PREVIEW_ITEM__":
                    self.ctrl.user_preview_items.append(item[1])
                    iid = f"user_row_{len(self.ctrl.user_preview_items)}"
                    self.ctrl.user_preview_item_by_iid[iid] = item[1]
                    self.user_tab.preview.add_item(item[1], len(self.ctrl.user_preview_items))
                elif isinstance(item, tuple) and item[0] == "__USER_PREVIEW_DONE__":
                    self.user_tab.finish_load(int(item[1] or 0))
                    self.status_var.set("用户作品加载完成")
                    self.total_progress_var.set(0)
                    self.progress.set_progress_visible(False)
                elif isinstance(item, tuple) and item[0] == "__USER_BUSY__":
                    self.user_tab.set_busy(bool(item[1]))
                elif isinstance(item, tuple) and item[0] == "__USER_ROW_STATUS_BY_ID__":
                    _, aweme_id, status, size_text = item
                    self.user_tab.preview.update_status(
                        str(aweme_id), str(status), size_text)
                elif isinstance(item, tuple) and item[0] == "__PREVIEW_DONE__":
                    count = int(item[1] or 0)
                    if self._unsupported_labels:
                        labels = "、".join(sorted(self._unsupported_labels))
                        self._unsupported_labels.clear()
                        messagebox.showwarning(
                            "暂不支持",
                            f"检测到：{labels}\n\n直播/直播回放链接暂不支持下载，"
                            "请移除相关链接后重试。")
                    self.status_var.set("解析完成")
                    self.total_progress_var.set(0)
                    self.progress.set_progress_visible(False)
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
                        is_single = (
                            source == "单个作品"
                            or source in ("video", "gallery", "music", "live", "collection")
                        )
                        self.link_tab.set_limit_disabled(is_single)
                        if is_single:
                            self.limit_var.set(0)
                    self.link_tab.update_download_count()
                    self.link_tab.preview.tree.bind("<<TreeviewSelect>>",
                                                     lambda _: self.link_tab.update_download_count())
                    # 单个作品（视频/图文）时启用评论页签
                    self.comments_tab.reset()
                    self.notebook.tab(self.comments_tab, state="disabled")
                    if len(self.ctrl.preview_items) == 1:
                        single = self.ctrl.preview_items[0]
                        media_type = getattr(single, "media_type", "") or ""
                        if media_type in ("视频", "图文"):
                            save_dir = str(
                                Path(self.path_var.get() or default_download_dir())
                                / "评论图片"
                                / f"{getattr(single, 'author_name', 'unknown') or 'unknown'}_{single.aweme_id}"
                            )
                            self.comments_tab.set_aweme(
                                single.aweme_id,
                                getattr(single, "title", "") or "",
                                getattr(single, "author_name", "") or "",
                                save_dir,
                            )
                            self.notebook.tab(self.comments_tab, state="normal")
                elif isinstance(item, tuple) and item[0] == "__ROW_STATUS_BY_ID__":
                    _, aweme_id, status, size_text = item
                    self.link_tab.preview.update_status(str(aweme_id), str(status), size_text)
                elif isinstance(item, tuple) and item[0] == "__TOTAL_PROGRESS__":
                    _, completed, total, success, failed, skipped = item
                    self.progress.set_progress_visible(True)
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
                elif isinstance(item, tuple) and item[0] == "__COMMENT_ITEM__":
                    self.comments_tab.add_comment(item[1])
                elif isinstance(item, tuple) and item[0] == "__COMMENT_THUMB__":
                    _, cid, index, path, is_live, nickname = item
                    self.comments_tab.add_image(cid, index, path, is_live, nickname)
                elif isinstance(item, tuple) and item[0] == "__COMMENT_BUSY__":
                    self.comments_tab.set_busy(bool(item[1]))
                elif isinstance(item, tuple) and item[0] == "__COMMENTS_DONE__":
                    _, count, image_count, failed_thumbs = item
                    self.comments_tab.finish_load(count, image_count, failed_thumbs)
                elif isinstance(item, tuple) and item[0] == "__COMMENTS_ERROR__":
                    self.comments_tab.show_load_error(str(item[1]))
                    self.status_var.set("评论加载失败")
                elif isinstance(item, tuple) and item[0] == "__COMMENT_DL_PROGRESS__":
                    _, current, total, success, failed, name = item
                    self.comments_tab.update_download_progress(
                        current, total, success, failed, name)
                elif isinstance(item, tuple) and item[0] == "__COMMENT_DL_DONE__":
                    _, success, failed, save_dir = item
                    self.comments_tab.finish_download(success, failed, save_dir)
                elif isinstance(item, tuple) and item[0] == "__COMMENT_ZOOM__":
                    _, ok, path, error = item
                    self.comments_tab.show_zoom_result(ok, path, error)
                elif isinstance(item, str):
                    self._log(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_output)
