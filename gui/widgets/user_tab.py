"""用户主页页签 — 子模式选择、作品预览与下载。"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk

from gui.theme import FONT, FONT_SMALL, TEXT_MUTED
from gui.widgets.link_tab import MODE_SHORT
from gui.widgets.preview_tab import PreviewTab
from gui.widgets.rounded_button import RoundedButton


class UserTab(ttk.Frame):
    def __init__(self, parent, on_load, on_start, on_pause, on_resume, on_stop,
                 on_history=None):
        super().__init__(parent, padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.on_load = on_load
        self.on_start = on_start

        self.mode_var = tk.StringVar(value=MODE_SHORT["post"])
        self.limit_var = tk.IntVar(value=0)
        self.increase_var = tk.BooleanVar(value=False)

        # ── Row 0 – URL + load ───────────────────────────────────
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.columnconfigure(1, weight=1)
        self.history_btn = RoundedButton(top, text="历史用户", style="ghost",
                                         height=28, command=on_history)
        self.history_btn.grid(row=0, column=0, sticky="w")
        ttk.Label(top, text="用户主页链接").grid(row=0, column=1, sticky="w",
                                                  padx=(8, 0))
        self.url_entry = ttk.Entry(top)
        self.url_entry.grid(row=0, column=2, sticky="ew", padx=(8, 8))
        self.load_btn = RoundedButton(top, text="加载作品", style="primary",
                                      command=on_load)
        self.load_btn.grid(row=0, column=3)

        # ── Row 1 – 下载内容 + 数量 ──────────────────────────────
        opts = ttk.Frame(self)
        opts.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(opts, text="下载内容").pack(side="left")
        self.mode_combo = ttk.Combobox(opts, textvariable=self.mode_var,
                                       values=list(MODE_SHORT.values()),
                                       state="readonly", width=9)
        self.mode_combo.pack(side="left", padx=(6, 12))
        ttk.Label(opts, text="数量").pack(side="left")
        self.limit_spin = ttk.Spinbox(opts, from_=0, to=999999,
                                      textvariable=self.limit_var, width=7)
        self.limit_spin.pack(side="left", padx=(4, 0))
        tk.Checkbutton(opts, text="增量", variable=self.increase_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT
                       ).pack(side="left", padx=(12, 0))

        # ── Row 2 – Preview table ────────────────────────────────
        self.preview = PreviewTab(self)
        self.preview.grid(row=2, column=0, sticky="nsew", pady=(0, 4))

        # ── Row 3 – Buttons ──────────────────────────────────────
        bar = ttk.Frame(self)
        bar.grid(row=3, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.dl_info = ttk.Label(bar, text="", foreground=TEXT_MUTED,
                                 font=FONT_SMALL)
        self.dl_info.grid(row=0, column=0, sticky="w")
        self.stop_btn = RoundedButton(bar, text="⏹ 终止", command=on_stop,
                                      style="danger", state="disabled")
        self.stop_btn.grid(row=0, column=4, padx=(6, 0))
        self.run_btn = RoundedButton(bar, text="开始下载", command=self._on_start_wrapper,
                                     style="primary")
        self.run_btn.grid(row=0, column=3, padx=(6, 0))
        self.resume_btn = RoundedButton(bar, text="▶ 继续", command=on_resume,
                                        style="ghost", state="disabled")
        self.resume_btn.grid(row=0, column=2, padx=(0, 6))
        self.pause_btn = RoundedButton(bar, text="⏸ 暂停", command=on_pause,
                                       style="ghost", state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=(0, 6))

    # ── public API ──────────────────────────────────────────────────

    def set_url(self, url: str):
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, str(url or ""))

    def get_url(self) -> str:
        return self.url_entry.get().strip()

    def get_sec_uid(self) -> str:
        match = re.search(r"/user/([A-Za-z0-9_-]+)", self.get_url())
        if match:
            return match.group(1)
        return ""

    def get_selected_mode(self) -> str:
        label = self.mode_var.get()
        for key, short in MODE_SHORT.items():
            if short == label:
                return key
        return "post"

    def get_limit(self) -> int:
        try:
            return max(0, int(self.limit_var.get()))
        except (TypeError, ValueError):
            return 0

    def get_increase(self) -> bool:
        return bool(self.increase_var.get())

    def set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.load_btn.configure(state=state)
        self.run_btn.configure(state=state)
        self.pause_btn.configure(state="normal" if busy else "disabled")
        self.resume_btn.configure(state="normal" if busy else "disabled")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def reset(self):
        self.preview.clear()
        self.update_download_count()

    def finish_load(self, count: int):
        self.dl_info.configure(text=f"共 {count} 个作品，勾选后点击「开始下载」")
        self.preview.tree.bind("<<TreeviewSelect>>",
                               lambda _: self.update_download_count())
        self.update_download_count()

    def update_download_count(self):
        selected = len(self.preview.get_selected_iids())
        total = len(self.preview._aweme_id_to_iid)
        if selected > 0:
            self.run_btn.configure(text=f"开始下载(已选{selected}个)")
            self.dl_info.configure(text=f"已选 {selected} / 共 {total} 个作品")
        else:
            self.run_btn.configure(text="开始下载")
            self.dl_info.configure(text=f"共 {total} 个作品")

    def _on_start_wrapper(self):
        self.update_download_count()
        self.on_start()
