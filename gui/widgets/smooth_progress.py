"""Canvas-drawn smooth progress bar with gradient fill.

The bar animates from its current value to the new target instead of
jumping, and the fill uses a blue gradient with a bright leading edge.
"""

import tkinter as tk

from gui.theme import BG, BLUE, BLUE_SOFT, BORDER, lerp_color
from gui.widgets.rounded_button import round_rect_points

_ANIM_MS = 16
_FILL_STEP = 4


class SmoothProgressBar(tk.Canvas):
    """A rounded progress bar whose fill eases toward its target value."""

    def __init__(self, parent, height=12, maximum=100.0, track_color=None,
                 canvas_bg=None, **kw):
        self._height = height
        self._maximum = float(maximum)
        self._value = 0.0
        self._target = 0.0
        self._anim_id = None
        self._track_color = track_color or BORDER
        bg = canvas_bg or BG
        super().__init__(parent, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)
        self._fill_ids = []
        self.bind("<Configure>", self._redraw)
        self._redraw()

    # ── public API ──────────────────────────────────────────────────

    def set_value(self, value):
        """Set the target value (0..maximum); the bar eases toward it."""
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        self._target = max(0.0, min(self._maximum, value))
        if self._anim_id is None:
            self._tick()

    def set_maximum(self, maximum):
        self._maximum = float(maximum)

    # ── internals ───────────────────────────────────────────────────

    def _tick(self):
        delta = self._target - self._value
        if abs(delta) < 0.4:
            self._value = self._target
            self._anim_id = None
            self._redraw()
            return
        self._value += delta * 0.22
        self._redraw()
        self._anim_id = self.after(_ANIM_MS, self._tick)

    def _redraw(self, _event=None):
        for item in self._fill_ids:
            self.delete(item)
        self._fill_ids = []

        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1:
            w = 200
        if h <= 1:
            h = self._height

        y1, y2 = 1, h - 1
        r = min(5, h // 2)

        # track
        self.create_polygon(round_rect_points(1, y1, w - 1, y2, r),
                            smooth=True, fill=self._track_color)

        # fill
        ratio = self._value / self._maximum if self._maximum else 0.0
        fill_w = max(0, ratio * (w - 2))
        if fill_w < 3:
            return
        x_end = min(w - 2, 1 + fill_w)
        if x_end - 1 <= 2 * r:
            # too narrow for rounded end — draw a plain bar
            self._fill_ids.append(self.create_rectangle(1, y1, x_end, y2,
                                                        fill=BLUE, width=0))
            return

        # gradient body (vertical stripes, left to right)
        for x in range(1, int(x_end) - r, _FILL_STEP):
            t = (x - 1) / max(1.0, x_end - 2)
            color = lerp_color(BLUE, BLUE_SOFT, t)
            self._fill_ids.append(
                self.create_line(x, y1 + 1, x, y2 - 1, fill=color, width=_FILL_STEP))

        # rounded right end + bright leading edge
        pts = round_rect_points(1, y1, x_end, y2, r)
        self._fill_ids.append(self.create_polygon(pts, smooth=True,
                                                  fill=BLUE_SOFT, width=0))
        self._fill_ids.append(
            self.create_line(x_end - 1, y1 + 1, x_end - 1, y2 - 1,
                             fill="#BFDBFE", width=1))
