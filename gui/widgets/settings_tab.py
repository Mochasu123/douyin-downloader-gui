"""Settings tab — download path, cookie, options, advanced."""

import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path

from gui.controller import default_download_dir


class SettingsTab(ttk.Frame):
    COOKIE_HINT = (
        "需要这 7 个字段，用分号空格隔开：\n"
        "passport_csrf_token=xxx; odin_tt=xxx; sessionid=xxx; "
        "sid_guard=xxx; sid_tt=xxx; uid_tt=xxx; n_mh=xxx"
    )

    def __init__(self, parent, path_var, cookie_var, retry_var,
                 browser_fallback_var,
                 on_save, on_open_dir, on_clear_log):
        super().__init__(parent, padding=(16, 12, 16, 8))

        # ── Row 0: Download path ─────────────────────────────────
        path_row = ttk.Frame(self)
        path_row.pack(fill="x")
        ttk.Label(path_row, text="下载目录", width=8, anchor="w").pack(side="left")
        ttk.Entry(path_row, textvariable=path_var).pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(path_row, text="选择", style="Tool.TButton",
                   command=lambda: self._browse_dir(path_var)).pack(side="left")

        # ── Row 1: Cookie ────────────────────────────────────────
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(10, 8))

        cookie_hdr = ttk.Frame(self)
        cookie_hdr.pack(fill="x")
        ttk.Label(cookie_hdr, text="Cookie", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self.cookie_status = ttk.Label(cookie_hdr, text="", foreground="#888",
                                        font=("Microsoft YaHei UI", 8))
        self.cookie_status.pack(side="left", padx=(10, 0))

        # Hint
        hint = ttk.Frame(self)
        hint.pack(fill="x", pady=(4, 0))
        ttk.Label(hint, text="", foreground="#666",
                  font=("Microsoft YaHei UI", 8)).pack(side="left")
        ttk.Label(hint, text=self.COOKIE_HINT, foreground="#999",
                  font=("Consolas", 7), wraplength=800).pack(side="left")

        cookie_text = tk.Text(self, height=3, wrap="word", font=("Consolas", 9))
        cookie_text.pack(fill="x", pady=(2, 0))
        cookie_text.insert("1.0", cookie_var.get())
        self.cookie_text = cookie_text

        def _sync_cookie(*_):
            val = cookie_text.get("1.0", "end").strip()
            cookie_var.set(val)
            self._update_cookie_status(val)
        cookie_text.bind("<<Modified>>", lambda e: (cookie_text.edit_modified(False), _sync_cookie()))
        self._update_cookie_status(cookie_var.get())

        # ── Row 2: Advanced ──────────────────────────────────────
        adv = ttk.Frame(self)
        adv.pack(fill="x", pady=(12, 0))
        ttk.Label(adv, text="失败重试").pack(side="left")
        ttk.Spinbox(adv, from_=0, to=20, textvariable=retry_var, width=5).pack(side="left", padx=(6, 0))
        tk.Checkbutton(adv, text="浏览器兜底", variable=browser_fallback_var,
                       relief="flat", bg="#F5F5F5", activebackground="#F5F5F5",
                       selectcolor="#F5F5F5").pack(side="left", padx=(16, 0))
        ttk.Label(adv, text="线程: 3（自动）", foreground="#aaa",
                  font=("Microsoft YaHei UI", 8)).pack(side="left", padx=(16, 0))

        # ── Row 4: Buttons ───────────────────────────────────────
        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="保存配置", command=on_save, style="Primary.TButton").pack(side="left")
        ttk.Button(btns, text="打开下载目录", command=on_open_dir, style="Tool.TButton").pack(
            side="left", padx=(12, 0))
        ttk.Button(btns, text="清空日志", command=on_clear_log, style="Tool.TButton").pack(
            side="left", padx=(12, 0))

    def _browse_dir(self, path_var):
        chosen = filedialog.askdirectory(initialdir=path_var.get() or str(Path.home()))
        if chosen:
            path_var.set(chosen)

    def get_cookie(self) -> str:
        return self.cookie_text.get("1.0", "end").strip()

    def _update_cookie_status(self, cookie_value: str):
        if not cookie_value.strip():
            self.cookie_status.configure(text="未设置", foreground="#E65100")
            return
        essential = ["passport_csrf_token", "odin_tt", "sessionid"]
        found = sum(1 for k in essential if k in cookie_value)
        if found >= 2:
            parts = [p.strip() for p in cookie_value.split(";") if p.strip()]
            count = len(parts)
            self.cookie_status.configure(
                text=f"✓ 已设置 ({count} 项)", foreground="#2E7D32")
        elif found >= 1:
            self.cookie_status.configure(
                text="⚠ 可能不完整", foreground="#E65100")
        else:
            self.cookie_status.configure(
                text="⚠ 格式异常", foreground="#C62828")
