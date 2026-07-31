"""Top banner — a soft light gradient with a thin blue accent line.

Redesigned as a light, premium-looking header: a very pale blue gradient
that fades into the page background, dark text, and a 2px blue accent
line along the bottom edge. No more large saturated blue surface.
"""

import tkinter as tk

from gui.theme import BG, BLUE, TEXT, TEXT_MUTED, FONT_TITLE, FONT_SMALL, lerp_color


class GradientHeader(tk.Canvas):
    """A light horizontal banner (pale blue → page colour) with a title.

    Redraws itself on resize; the title/subtitle can be updated at runtime.
    """

    STOPS = ("#EAF2FF", "#F4F8FF", BG)

    def __init__(self, parent, title="", subtitle="", height=60, **kw):
        self._title = title
        self._subtitle = subtitle
        self._height = height
        super().__init__(parent, height=height, bg=BG,
                         highlightthickness=0, bd=0, **kw)
        self.bind("<Configure>", self._redraw)
        self._redraw()

    # ── public API ──────────────────────────────────────────────────

    def set_title(self, text):
        self._title = text
        self._redraw()

    def set_subtitle(self, text):
        self._subtitle = text
        self._redraw()

    # ── internals ───────────────────────────────────────────────────

    def _redraw(self, _event=None):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            return
        h = self._height
        segs = len(self.STOPS) - 1
        for y in range(h):
            pos = y / h * segs
            i = min(int(pos), segs - 1)
            color = lerp_color(self.STOPS[i], self.STOPS[i + 1], pos - i)
            self.create_line(0, y, w, y, fill=color)

        cy = h // 2
        if self._title:
            self.create_text(26, cy - 12, anchor="w", text=self._title,
                             font=FONT_TITLE, fill=TEXT)
        if self._subtitle:
            self.create_text(28, cy + 10, anchor="w", text=self._subtitle,
                             font=FONT_SMALL, fill=TEXT_MUTED)

        # thin blue accent line along the bottom edge
        self.create_line(0, h - 1, w, h - 1, fill=BLUE, width=2)
