"""Small status dot with a breathing animation while downloading."""

import tkinter as tk

from gui.theme import (
    BG, SUCCESS, FAILED, SKIPPED, DOWNLOADING, PENDING,
)

_STATE_COLORS = {
    "success": SUCCESS,
    "failed": FAILED,
    "downloading": DOWNLOADING,
    "skipped": SKIPPED,
    "pending": PENDING,
}

_PULSE_MS = 70


class StatusDot(tk.Canvas):
    """A 12px status circle; ``downloading`` pulses with a breathing effect."""

    def __init__(self, parent, size=12, state="pending", canvas_bg=None, **kw):
        self._size = size
        self._state = state
        self._pulse_step = 0
        self._pulse_id = None
        bg = canvas_bg or BG
        super().__init__(parent, width=size + 6, height=size + 6, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", self._draw)
        self.set_state(state)

    # ── public API ──────────────────────────────────────────────────

    def set_state(self, state):
        """state: success | failed | downloading | skipped | pending."""
        if state not in _STATE_COLORS:
            state = "pending"
        self._state = state
        if self._pulse_id:
            self.after_cancel(self._pulse_id)
            self._pulse_id = None
        self._pulse_step = 0
        self._draw()
        if state == "downloading":
            self._pulse(0)

    # ── internals ───────────────────────────────────────────────────

    def _draw(self, _event=None):
        self.delete("all")
        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 1:
            cw = self._size + 6
        if ch <= 1:
            ch = self._size + 6
        cx, cy = cw / 2, ch / 2
        base = self._size / 2
        if self._state == "downloading":
            phase = (self._pulse_step % 16) / 16.0
            r = base + 2.2 * abs(phase * 2 - 1)  # 0 → 2.2px breathing
        else:
            r = base
        color = _STATE_COLORS[self._state]
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color,
                         outline="", width=0)

    def _pulse(self, step):
        if self._state != "downloading":
            return
        self._pulse_step = step
        self._draw()
        self._pulse_id = self.after(_PULSE_MS, lambda: self._pulse(step + 1))
