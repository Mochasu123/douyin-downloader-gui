"""Progress area — smooth animated bars, status labels and a state dot."""

import tkinter as tk
from tkinter import ttk

from gui.theme import FONT_BOLD, TEXT
from gui.widgets.smooth_progress import SmoothProgressBar
from gui.widgets.status_dot import StatusDot


class ProgressPanel(ttk.Frame):
    """Two-row panel: total progress + per-file progress.

    Both bars ease toward their target when the bound variables change;
    the status dot reflects the current state (idle / downloading / done).
    """

    def __init__(self, parent, total_progress_var, file_progress_var,
                 status_var, file_status_var):
        super().__init__(parent, style="Card.TFrame", padding=(14, 10, 14, 12))
        self.columnconfigure(2, weight=1)

        self._total_var = total_progress_var
        self._file_var = file_progress_var
        self._status_var = status_var
        self._pct_text = "0%"
        self._pct_visible = False

        # ── row 0: total progress ─────────────────────────────────
        self.dot = StatusDot(self, state="pending", canvas_bg="#FFFFFF")
        self.dot.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 8))

        ttk.Label(self, textvariable=status_var, style="Card.TLabel",
                  justify="left", wraplength=760
                  ).grid(row=0, column=1, sticky="w")

        self.total_bar = SmoothProgressBar(self, height=10, canvas_bg="#FFFFFF")
        self.total_bar.grid(row=0, column=2, sticky="ew", padx=(8, 4))

        self.pct_label = ttk.Label(self, text="0%", width=5, style="Card.TLabel",
                                   foreground="#2563EB", font=FONT_BOLD)
        self.pct_label.grid(row=0, column=3, sticky="e")

        # ── row 1: file progress ──────────────────────────────────
        ttk.Label(self, textvariable=file_status_var, width=36,
                  style="Card.TLabel", foreground=TEXT, justify="left",
                  wraplength=760
                  ).grid(row=1, column=1, sticky="w")

        self.file_bar = SmoothProgressBar(self, height=10, canvas_bg="#FFFFFF")
        self.file_bar.grid(row=1, column=2, sticky="ew", padx=(8, 4))

        # ── watch the bound variables ─────────────────────────────
        total_progress_var.trace_add("write", self._on_total_change)
        file_progress_var.trace_add("write", self._on_file_change)
        status_var.trace_add("write", self._on_status_change)
        self._on_total_change()
        self._on_status_change()
        self.set_progress_visible(False)

    # ── public API ──────────────────────────────────────────────────

    def set_progress_visible(self, visible: bool):
        """只在下载阶段显示进度条与百分数，解析/空闲阶段全部隐藏。"""
        self._pct_visible = bool(visible)
        if self._pct_visible:
            self.total_bar.grid(row=0, column=2, sticky="ew", padx=(8, 4))
            self.file_bar.grid(row=1, column=2, sticky="ew", padx=(8, 4))
        else:
            self.total_bar.grid_remove()
            self.file_bar.grid_remove()
        self._refresh_pct()

    # ── internals ──────────────────────────────────────────────────

    def _on_total_change(self, *_):
        try:
            value = float(self._total_var.get())
        except (TypeError, ValueError):
            value = 0.0
        self.total_bar.set_value(value)
        self._pct_text = "%d%%" % int(round(value))
        self._refresh_pct()

    def _refresh_pct(self):
        self.pct_label.configure(text=self._pct_text if self._pct_visible else "")

    def _on_file_change(self, *_):
        try:
            value = float(self._file_var.get())
        except (TypeError, ValueError):
            value = 0.0
        self.file_bar.set_value(value)

    def _on_status_change(self, *_):
        text = str(self._status_var.get())
        if "空闲" in text or "已暂停" in text:
            state = "pending" if "空闲" in text else "skipped"
        elif "已终止" in text:
            state = "failed"
        elif "失败" in text:
            state = "failed"
        elif "完成" in text or "成功" in text:
            state = "success"
        else:
            state = "downloading"
        self.dot.set_state(state)
