"""Canvas-drawn rounded button with smooth hover colour animation.

Replaces ttk buttons where a modern look matters. Supports a small
``configure(text/state/command/style=...)`` API compatible with the
ttk.Button usage in the rest of the GUI.
"""

import tkinter as tk
import tkinter.font as tkfont

from gui.theme import (
    BG, BG_PANEL, BLUE, BLUE_PALE, BORDER, FONT,
    FAILED, FAILED_BG,
    lerp_color,
)

_STYLES = {
    "primary": {
        "bg": BG_PANEL, "hover": BLUE_PALE, "active": "#BFDBFE",
        "fg": BLUE, "border": BLUE,
    },
    "ghost": {
        "bg": BG_PANEL, "hover": BLUE_PALE, "active": "#BFDBFE",
        "fg": BLUE, "border": BORDER,
    },
    "danger": {
        "bg": BG_PANEL, "hover": FAILED_BG, "active": "#FEE2E2",
        "fg": FAILED, "border": "#FECACA",
    },
}

_DISABLED_BG = "#E2E8F0"
_DISABLED_FG = "#94A3B8"

_ANIM_STEPS = 10
_ANIM_MS = 14

_FONT = FONT


def round_rect_points(x1, y1, x2, y2, r):
    """Vertex list for a rounded rectangle polygon (smooth=True)."""
    return [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]


class RoundedButton(tk.Canvas):
    """A flat rounded button drawn on a Canvas.

    ``style`` selects the palette: ``primary`` (blue fill), ``ghost``
    (white fill, blue text, subtle border) or ``danger`` (white fill,
    red text). Hover / pressed states animate the fill colour.
    """

    def __init__(self, parent, text="", command=None, style="ghost",
                 height=30, radius=8, font=None, canvas_bg=None, **kw):
        self._text = text
        self._command = command
        self._style_name = style
        self._state = "normal"
        self._height = height
        self._radius = radius
        self._font = font or _FONT
        self._cur_bg = None
        self._anim_id = None
        self._pressed = False

        bg = canvas_bg or BG
        super().__init__(parent, height=height, bg=bg,
                         highlightthickness=0, bd=0, **kw)

        self._auto_width = "width" not in kw
        self._resize_for_text()

        self._rect_id = None
        self._text_id = None

        self.bind("<Configure>", self._redraw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.configure(cursor="hand2")

        self._redraw()

    # ── public API ──────────────────────────────────────────────────

    def configure(self, **kw):
        """Support the ttk.Button-style calls used by the GUI."""
        if "text" in kw:
            self._text = kw.pop("text")
            if self._auto_width:
                self._resize_for_text()
        if "command" in kw:
            self._command = kw.pop("command")
        if "state" in kw:
            self._state = kw.pop("state")
            self._cur_bg = None
            if self._anim_id:
                self.after_cancel(self._anim_id)
                self._anim_id = None
        if "style" in kw:
            self._style_name = kw.pop("style")
            self._cur_bg = None
        if kw:
            super().configure(**kw)
        self._redraw()

    def set_text(self, text):
        self.configure(text=text)

    def set_state(self, state):
        self.configure(state=state)

    # ── internals ───────────────────────────────────────────────────

    def _style(self):
        return _STYLES.get(self._style_name, _STYLES["ghost"])

    def _resize_for_text(self):
        f = tkfont.Font(font=self._font)
        w = f.measure(self._text) + 30
        super().configure(width=max(64, w))

    def _base_bg(self):
        if self._state == "disabled":
            return _DISABLED_BG
        return self._style()["bg"]

    def _redraw(self, _event=None):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1:
            w = 100
        if h <= 1:
            h = self._height

        if self._state == "disabled":
            bg, fg, border = _DISABLED_BG, _DISABLED_FG, None
        else:
            style = self._style()
            bg = self._cur_bg if self._cur_bg is not None else style["bg"]
            if self._cur_bg is None:
                self._cur_bg = bg
            fg, border = style["fg"], style.get("border")

        r = min(self._radius, h // 2, w // 2)
        pts = round_rect_points(1, 1, w - 1, h - 1, r)
        self._rect_id = self.create_polygon(
            pts, smooth=True, fill=bg,
            outline=border if border else "", width=1 if border else 0)
        self._text_id = self.create_text(
            w / 2, h / 2, text=self._text, font=self._font, fill=fg)

    def _animate_to(self, target):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
        start = self._cur_bg or self._base_bg()
        step = [0]

        def _tick():
            step[0] += 1
            t = min(1.0, step[0] / _ANIM_STEPS)
            color = lerp_color(start, target, t)
            if self._rect_id:
                self.itemconfigure(self._rect_id, fill=color)
            self._cur_bg = color
            if t >= 1.0:
                self._anim_id = None
                return
            self._anim_id = self.after(_ANIM_MS, _tick)

        _tick()

    def _on_enter(self, _event):
        if self._state == "disabled":
            return
        self._animate_to(self._style()["hover"])

    def _on_leave(self, _event):
        if self._state == "disabled":
            return
        self._animate_to(self._base_bg())

    def _on_press(self, _event):
        if self._state == "disabled":
            return
        self._pressed = True
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
        color = self._style()["active"]
        if self._rect_id:
            self.itemconfigure(self._rect_id, fill=color)
        self._cur_bg = color

    def _on_release(self, event):
        if not self._pressed:
            return
        self._pressed = False
        inside = (0 <= event.x <= self.winfo_width() and
                  0 <= event.y <= self.winfo_height())
        target = self._style()["hover"] if inside else self._base_bg()
        self._animate_to(target)
        if inside and self._state != "disabled" and self._command:
            self._command()
