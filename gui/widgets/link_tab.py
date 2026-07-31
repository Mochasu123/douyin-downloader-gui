"""Link download tab — URL → preview → controls at bottom."""

import tkinter as tk
from tkinter import ttk

from gui.theme import FONT, FONT_SMALL, TEXT_MUTED
from gui.widgets.preview_tab import PreviewTab
from gui.widgets.rounded_button import RoundedButton

MODE_KEYS = ["post", "like", "mix", "music", "collect", "collectmix"]
MODE_SHORT = {
    "post": "主页", "like": "喜欢", "mix": "合集",
    "music": "音乐", "collect": "收藏", "collectmix": "收藏夹合集",
}


class LinkTab(ttk.Frame):
    def __init__(self, parent, urls_var, limit_var,
                 cover_var, music_var, avatar_var, json_var, increase_var,
                 on_preview, on_start, on_pause, on_resume, on_stop):
        super().__init__(parent, padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        self.on_preview = on_preview
        self.on_start = on_start

        self.mode_vars: dict[str, tk.BooleanVar] = {}
        for key in MODE_KEYS:
            self.mode_vars[key] = tk.BooleanVar(value=(key == "post"))

        self.cover_var = cover_var
        self.music_var = music_var
        self.avatar_var = avatar_var
        self.json_var = json_var
        self.increase_var = increase_var
        self.limit_var = limit_var

        # ── Row 0 – URL input ────────────────────────────────────
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)

        ttk.Label(top, text="下载链接，一行一个", font=FONT
                  ).grid(row=0, column=0, sticky="w")

        self.urls_text = tk.Text(top, height=6, wrap="word",
                                 bg="#FFFFFF", fg="#0F172A", font=FONT,
                                 insertbackground="#2563EB", relief="flat",
                                 highlightthickness=1, highlightbackground="#E2E8F0",
                                 highlightcolor="#2563EB", padx=8, pady=6)
        self.urls_text.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 8))
        self.urls_text.insert("1.0", urls_var.get())

        RoundedButton(top, text="解析链接", command=on_preview,
                      style="primary").grid(row=2, column=1, sticky="e", pady=(0, 4))

        # ── Row 1 – Preview table ────────────────────────────────
        self.preview = PreviewTab(self)
        self.preview.grid(row=2, column=0, sticky="nsew", pady=(0, 4))

        # ── Row 2 – Controls (below table) ───────────────────────
        ctrl = ttk.Frame(self)
        ctrl.grid(row=3, column=0, sticky="ew")
        ctrl.columnconfigure(0, weight=1)

        ctrl_inner = ttk.Frame(ctrl)
        ctrl_inner.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(ctrl_inner, text="下载内容").pack(side="left")
        for key in MODE_KEYS[:4]:
            tk.Checkbutton(ctrl_inner, text=MODE_SHORT[key],
                           variable=self.mode_vars[key],
                           relief="flat", bg="#FFFFFF",
                           activebackground="#EFF6FF",
                           selectcolor="#FFFFFF", font=FONT,
                           fg="#0F172A").pack(side="left", padx=(6, 0))
        ttk.Separator(ctrl_inner, orient="vertical").pack(side="left", padx=(8, 8), fill="y")
        ttk.Label(ctrl_inner, text="数量").pack(side="left")
        self.limit_spin = ttk.Spinbox(ctrl_inner, from_=0, to=999999, textvariable=limit_var, width=7)
        self.limit_spin.pack(side="left", padx=(4, 0))

        ctrl_opts = ttk.Frame(ctrl)
        ctrl_opts.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        tk.Checkbutton(ctrl_opts, text="封面", variable=cover_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT).pack(side="left")
        tk.Checkbutton(ctrl_opts, text="音乐", variable=music_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT).pack(side="left", padx=(8, 0))
        tk.Checkbutton(ctrl_opts, text="头像", variable=avatar_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT).pack(side="left", padx=(8, 0))
        tk.Checkbutton(ctrl_opts, text="JSON", variable=json_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT).pack(side="left", padx=(8, 0))
        tk.Checkbutton(ctrl_opts, text="增量", variable=increase_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT).pack(side="left", padx=(8, 0))

        # ── Row 3 – Bottom bar ───────────────────────────────────
        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)

        self.dl_info = ttk.Label(bar, text="", foreground=TEXT_MUTED,
                                  font=FONT_SMALL)
        self.dl_info.grid(row=0, column=0, sticky="w")

        self.pause_btn = RoundedButton(bar, text="⏸ 暂停", command=on_pause,
                                       style="ghost", state="disabled")
        self.pause_btn.grid(row=0, column=1, padx=(0, 6))
        self.resume_btn = RoundedButton(bar, text="▶ 继续", command=on_resume,
                                        style="ghost", state="disabled")
        self.resume_btn.grid(row=0, column=2, padx=(0, 6))
        self.run_btn = RoundedButton(bar, text="开始下载", command=self._on_start_wrapper,
                                     style="primary")
        self.run_btn.grid(row=0, column=3, padx=(6, 0))
        self.stop_btn = RoundedButton(bar, text="⏹ 终止", command=on_stop,
                                      style="danger", state="disabled")
        self.stop_btn.grid(row=0, column=4, padx=(6, 0))

    # ── public API ──────────────────────────────────────────────────

    def set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.run_btn.configure(state=state)
        self.pause_btn.configure(state="normal" if busy else "disabled")
        self.resume_btn.configure(state="normal" if busy else "disabled")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def get_urls(self) -> list[str]:
        return [l.strip() for l in self.urls_text.get("1.0", "end").splitlines() if l.strip()]

    def get_selected_modes(self) -> list[str]:
        return [k for k in MODE_KEYS if self.mode_vars[k].get()]

    def set_limit_disabled(self, disabled: bool):
        self.limit_spin.configure(state="disabled" if disabled else "normal")

    def update_download_count(self):
        sel = len(self.preview.get_selected_iids())
        total = len(self.preview._aweme_id_to_iid)
        if sel > 0:
            self.run_btn.configure(text=f"开始下载(已选{sel}个)")
            self.dl_info.configure(text=f"已选 {sel} / 共 {total} 个作品")
        else:
            self.run_btn.configure(text="开始下载")
            self.dl_info.configure(text=f"共 {total} 个作品")

    # ── internal ────────────────────────────────────────────────────

    def _on_start_wrapper(self):
        self.update_download_count()
        self.on_start()
