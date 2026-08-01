"""Link download tab — URL → preview → compact controls at bottom."""

import tkinter as tk
from tkinter import ttk

from gui.theme import FONT, FONT_SMALL, TEXT_MUTED
from gui.widgets.preview_tab import PreviewTab
from gui.widgets.rounded_button import RoundedButton
from utils.validators import extract_url_from_line

MODE_SHORT = {
    "post": "主页", "like": "喜欢", "mix": "合集",
    "music": "音乐", "collect": "收藏", "collectmix": "收藏夹合集",
}


class LinkTab(ttk.Frame):
    def __init__(self, parent, urls_var,
                 on_preview, on_start, on_pause, on_resume, on_stop,
                 on_history=None):
        super().__init__(parent, padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self.on_preview = on_preview
        self.on_start = on_start

        # ── Row 0 – URL input ────────────────────────────────────
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="下载链接，一行一个", font=FONT
                  ).grid(row=0, column=0, sticky="w")

        self.urls_text = tk.Text(top, height=6, wrap="word",
                                 bg="#FFFFFF", fg="#0F172A", font=FONT,
                                 insertbackground="#2563EB", relief="flat",
                                 highlightthickness=1, highlightbackground="#E2E8F0",
                                 highlightcolor="#2563EB", padx=8, pady=6)
        self.urls_text.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(6, 8))
        self.urls_text.insert("1.0", urls_var.get())

        self.history_btn = RoundedButton(top, text="历史链接", style="ghost",
                                         height=28, command=on_history)
        self.history_btn.grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.type_label = ttk.Label(top, text="", foreground="#2563EB",
                                    font=FONT_SMALL)
        self.type_label.grid(row=2, column=1, sticky="w", padx=(8, 8), pady=(0, 4))

        RoundedButton(top, text="解析链接", command=on_preview,
                      style="primary").grid(row=2, column=2, sticky="e", pady=(0, 4))

        # ── Row 1 – Preview table ────────────────────────────────
        self.preview = PreviewTab(self)
        self.preview.grid(row=1, column=0, sticky="nsew", pady=(0, 4))

        # ── Row 2 – Controls (below table) ───────────────────────
        ctrl = ttk.Frame(self)
        ctrl.grid(row=2, column=0, sticky="ew")

        # 右侧操作按钮先 pack，保持右侧对齐
        self.stop_btn = RoundedButton(ctrl, text="⏹ 终止", command=on_stop,
                                      style="danger", state="disabled")
        self.stop_btn.pack(side="right", padx=(6, 0))
        self.run_btn = RoundedButton(ctrl, text="开始下载", command=self._on_start_wrapper,
                                     style="primary")
        self.run_btn.pack(side="right", padx=(6, 0))
        self.resume_btn = RoundedButton(ctrl, text="▶ 继续", command=on_resume,
                                        style="ghost", state="disabled")
        self.resume_btn.pack(side="right", padx=(0, 6))
        self.pause_btn = RoundedButton(ctrl, text="⏸ 暂停", command=on_pause,
                                       style="ghost", state="disabled")
        self.pause_btn.pack(side="right", padx=(0, 6))

        # ── Row 3 – Status line ──────────────────────────────────
        self.dl_info = ttk.Label(self, text="", foreground=TEXT_MUTED,
                                 font=FONT_SMALL)
        self.dl_info.grid(row=3, column=0, sticky="w")

    # ── public API ──────────────────────────────────────────────────

    def set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self.run_btn.configure(state=state)
        self.pause_btn.configure(state="normal" if busy else "disabled")
        self.resume_btn.configure(state="normal" if busy else "disabled")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def get_urls(self) -> list[str]:
        urls = []
        for line in self.urls_text.get("1.0", "end").splitlines():
            line = line.strip()
            if not line:
                continue
            extracted = extract_url_from_line(line)
            urls.append(extracted or line)
        return urls

    def get_selected_modes(self) -> list[str]:
        return ["post"]

    def set_limit_disabled(self, disabled: bool):
        # 链接页不再有数量输入框；单作品/列表类型自动处理
        return

    def set_type_label(self, text: str):
        self.type_label.configure(text=str(text or ""))

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
