"""Settings tab — download path, cookie (locked by default), options.

The cookie has a lock state machine:
  * locked (default): masked, read-only; 👁 查看 reveals it read-only;
    ✏️ 修改 switches into edit mode.
  * editing: real value shown and editable; ✕ 取消 reverts and re-locks;
    saving persists the edit and re-locks.

The 保存配置 button is disabled until a real change is detected.
"""

import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path

from gui.controller import default_download_dir
from gui.theme import FONT, FONT_MONO, FONT_SECTION, FONT_SMALL
from gui.widgets.rounded_button import RoundedButton


class SettingsTab(ttk.Frame):
    COOKIE_HINT = (
        "需要这 7 个字段，用分号空格隔开：\n"
        "passport_csrf_token=xxx; odin_tt=xxx; sessionid=xxx; "
        "sid_guard=xxx; sid_tt=xxx; uid_tt=xxx; n_mh=xxx"
    )

    VIDEO_QUALITY_LABELS = ("最高", "1440p", "1080p", "720p", "540p", "480p", "360p", "最低")

    def __init__(self, parent, path_var, cookie_var, retry_var,
                 browser_fallback_var, video_quality_var,
                 cover_var, music_var, avatar_var, json_var,
                 increase_var, homepage_screenshot_var, live_photo_merge_var,
                 on_save, on_open_dir):
        super().__init__(parent, padding=(16, 12, 16, 8))
        self.on_save = on_save

        # refs for change detection
        self.path_var_ref = path_var
        self.retry_var_ref = retry_var
        self.fallback_var_ref = browser_fallback_var
        self.cookie_var_ref = cookie_var
        self.video_quality_var_ref = video_quality_var
        self.cover_var_ref = cover_var
        self.music_var_ref = music_var
        self.avatar_var_ref = avatar_var
        self.json_var_ref = json_var
        self.increase_var_ref = increase_var
        self.homepage_screenshot_var_ref = homepage_screenshot_var
        self.live_photo_merge_var_ref = live_photo_merge_var

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
        ttk.Label(cookie_hdr, text="Cookie", font=FONT_SECTION).pack(side="left")
        self.cookie_status = ttk.Label(cookie_hdr, text="", foreground="#888",
                                        font=FONT_SMALL)
        self.cookie_status.pack(side="left", padx=(10, 0))
        self.modify_btn = tk.Button(cookie_hdr, text="✏️ 修改", relief="flat", bd=0,
                                    bg="#FFFFFF", fg="#2563EB",
                                    activebackground="#EFF6FF",
                                    disabledforeground="#94A3B8",
                                    font=FONT_SMALL, cursor="hand2",
                                    command=self._on_modify_clicked)
        self.modify_btn.pack(side="right", padx=(0, 8))
        self.eye_btn = tk.Button(cookie_hdr, text="👁 查看", relief="flat", bd=0,
                                 bg="#FFFFFF", fg="#2563EB",
                                 activebackground="#EFF6FF",
                                 disabledforeground="#94A3B8",
                                 font=FONT_SMALL, cursor="hand2",
                                 command=self._toggle_cookie_visibility)
        self.eye_btn.pack(side="right")

        # Hint
        hint = ttk.Frame(self)
        hint.pack(fill="x", pady=(6, 4))
        ttk.Label(hint, text=self.COOKIE_HINT, foreground="#94A3B8",
                  font=FONT_MONO, wraplength=820).pack(side="left")

        cookie_text = tk.Text(self, height=4, wrap="word", font=FONT_MONO,
                              bg="#FFFFFF", fg="#0F172A",
                              insertbackground="#2563EB", relief="flat",
                              highlightthickness=1, highlightbackground="#E2E8F0",
                              highlightcolor="#2563EB", padx=10, pady=8)
        cookie_text.pack(fill="x", pady=(2, 0))
        self.cookie_text = cookie_text
        cookie_text.bind("<<Modified>>", self._on_cookie_modified)

        # ── Row 2: Advanced ──────────────────────────────────────
        adv = ttk.Frame(self)
        adv.pack(fill="x", pady=(14, 0))
        ttk.Label(adv, text="失败重试").pack(side="left")
        ttk.Spinbox(adv, from_=0, to=20, textvariable=retry_var, width=5).pack(side="left", padx=(6, 0))
        tk.Checkbutton(adv, text="浏览器兜底", variable=browser_fallback_var,
                       relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                       selectcolor="#FFFFFF", fg="#0F172A", font=FONT
                       ).pack(side="left", padx=(16, 0))
        ttk.Label(adv, text="线程: 3（自动）", foreground="#94A3B8",
                  font=FONT_SMALL).pack(side="left", padx=(16, 0))

        # ── Row 3: Video quality ──────────────────────────────────
        quality_row = ttk.Frame(self)
        quality_row.pack(fill="x", pady=(14, 0))
        ttk.Label(quality_row, text="视频画质").pack(side="left")
        ttk.Combobox(quality_row, textvariable=video_quality_var,
                     values=self.VIDEO_QUALITY_LABELS, state="readonly", width=8
                     ).pack(side="left", padx=(6, 0))

        # ── Row: Download options (moved from link tab) ──────────
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(self, text="下载选项", font=FONT_SECTION).pack(anchor="w")
        opts1 = ttk.Frame(self)
        opts1.pack(fill="x", pady=(8, 2))
        for var, text in ((cover_var, "封面"), (music_var, "音乐"),
                          (avatar_var, "头像"), (json_var, "JSON")):
            tk.Checkbutton(opts1, text=text, variable=var,
                           relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                           selectcolor="#FFFFFF", fg="#0F172A", font=FONT
                           ).pack(side="left", padx=(0, 14))
        opts2 = ttk.Frame(self)
        opts2.pack(fill="x", pady=(2, 0))
        for var, text in ((increase_var, "增量"),
                          (homepage_screenshot_var, "主页截图"),
                          (live_photo_merge_var, "动图合并")):
            tk.Checkbutton(opts2, text=text, variable=var,
                           relief="flat", bg="#FFFFFF", activebackground="#EFF6FF",
                           selectcolor="#FFFFFF", fg="#0F172A", font=FONT
                           ).pack(side="left", padx=(0, 14))

        # ── Row 4: Buttons ───────────────────────────────────────
        btns = ttk.Frame(self)
        btns.pack(fill="x", pady=(12, 0))
        self.save_btn = RoundedButton(btns, text="保存配置", style="primary",
                                      state="disabled",
                                      command=self._on_save_wrapper)
        self.save_btn.pack(side="left")
        RoundedButton(btns, text="打开下载目录", command=on_open_dir, style="ghost"
                      ).pack(side="left", padx=(12, 0))

        # ── cookie lock state + change detection baselines ───────
        self._saved_cookie = cookie_var.get()
        self._real_cookie = self._saved_cookie
        self._cookie_editing = False
        self._cookie_visible = False
        self._base_path = path_var.get()
        self._base_retry = retry_var.get()
        self._base_fallback = browser_fallback_var.get()
        self._base_video_quality = video_quality_var.get()
        self._base_cover = cover_var.get()
        self._base_music = music_var.get()
        self._base_avatar = avatar_var.get()
        self._base_json = json_var.get()
        self._base_increase = increase_var.get()
        self._base_homepage = homepage_screenshot_var.get()
        self._base_live_merge = live_photo_merge_var.get()

        path_var.trace_add("write", self._update_save_state)
        retry_var.trace_add("write", self._update_save_state)
        browser_fallback_var.trace_add("write", self._update_save_state)
        video_quality_var.trace_add("write", self._update_save_state)
        for var in (cover_var, music_var, avatar_var, json_var,
                    increase_var, homepage_screenshot_var, live_photo_merge_var):
            var.trace_add("write", self._update_save_state)

        self._lock_cookie()
        self._update_cookie_status(self._real_cookie)
        self._update_save_state()

    # ── public API ──────────────────────────────────────────────────

    def get_cookie(self) -> str:
        return self._real_cookie

    # ── save gating ─────────────────────────────────────────────────

    def _update_save_state(self, *_):
        changed = (
            self.path_var_ref.get() != self._base_path
            or int(self.retry_var_ref.get()) != self._base_retry
            or bool(self.fallback_var_ref.get()) != self._base_fallback
            or self.video_quality_var_ref.get() != self._base_video_quality
            or bool(self.cover_var_ref.get()) != self._base_cover
            or bool(self.music_var_ref.get()) != self._base_music
            or bool(self.avatar_var_ref.get()) != self._base_avatar
            or bool(self.json_var_ref.get()) != self._base_json
            or bool(self.increase_var_ref.get()) != self._base_increase
            or bool(self.homepage_screenshot_var_ref.get()) != self._base_homepage
            or bool(self.live_photo_merge_var_ref.get()) != self._base_live_merge
            or self._real_cookie != self._saved_cookie
        )
        self.save_btn.configure(state="normal" if changed else "disabled")

    def _on_save_wrapper(self):
        if self.on_save():
            self._saved_cookie = self._real_cookie
            self._base_path = self.path_var_ref.get()
            self._base_retry = int(self.retry_var_ref.get())
            self._base_fallback = bool(self.fallback_var_ref.get())
            self._base_video_quality = self.video_quality_var_ref.get()
            self._base_cover = bool(self.cover_var_ref.get())
            self._base_music = bool(self.music_var_ref.get())
            self._base_avatar = bool(self.avatar_var_ref.get())
            self._base_json = bool(self.json_var_ref.get())
            self._base_increase = bool(self.increase_var_ref.get())
            self._base_homepage = bool(self.homepage_screenshot_var_ref.get())
            self._base_live_merge = bool(self.live_photo_merge_var_ref.get())
            self._lock_cookie()
            self._update_save_state()

    # ── cookie lock state machine ───────────────────────────────────

    def _lock_cookie(self):
        """Re-lock the cookie field; masks content, read-only."""
        self._cookie_editing = False
        self._cookie_visible = False
        self._apply_cookie_display()
        self._refresh_cookie_controls()

    def _on_modify_clicked(self):
        if self._cookie_editing:
            self._real_cookie = self._saved_cookie
            self._cookie_editing = False
            self._lock_cookie()
            self._update_save_state()
        elif self._real_cookie:
            self._cookie_editing = True
            self._cookie_visible = True
            self._apply_cookie_display()
            self._refresh_cookie_controls()

    def _toggle_cookie_visibility(self):
        if self._cookie_editing:
            return  # while editing the value is always visible
        self._cookie_visible = not self._cookie_visible
        self._apply_cookie_display()

    def _refresh_cookie_controls(self):
        has_cookie = bool(self._real_cookie)
        if self._cookie_editing:
            self.eye_btn.configure(state="disabled")
            self.modify_btn.configure(text="✕ 取消", state="normal")
        else:
            self.eye_btn.configure(state="normal" if has_cookie else "disabled")
            self.modify_btn.configure(text="✏️ 修改",
                                      state="normal" if has_cookie else "disabled")

    def _apply_cookie_display(self):
        """Show the real cookie only while visible; otherwise mask it."""
        self.cookie_text.configure(state="normal")
        self.cookie_text.delete("1.0", "end")
        if self._cookie_visible:
            self.cookie_text.insert("1.0", self._real_cookie)
            self.cookie_text.configure(
                state="normal" if self._cookie_editing else "disabled")
        else:
            self.cookie_text.insert("1.0", "●" * len(self._real_cookie))
            self.cookie_text.configure(state="disabled")
        self.cookie_text.edit_modified(False)

    def _on_cookie_modified(self, _event=None):
        self.cookie_text.edit_modified(False)
        if not self._cookie_editing:
            return  # masked/read-only display — never overwrite the real value
        self._real_cookie = self.cookie_text.get("1.0", "end").strip()
        self.cookie_var_ref.set(self._real_cookie)
        self._update_cookie_status(self._real_cookie)
        self._update_save_state()

    # ── misc ────────────────────────────────────────────────────────

    def _browse_dir(self, path_var):
        chosen = filedialog.askdirectory(initialdir=path_var.get() or str(Path.home()))
        if chosen:
            path_var.set(chosen)

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
