"""ttk theme and styling for Douyin Downloader GUI — modern blue/white.

Applies a ``clam``-based theme with blue gradient accents, a clean white
background, colour-coded Treeview status tags, and refined spacing.
"""

from tkinter import ttk
import tkinter as tk

# ── palette ──────────────────────────────────────────────────────────
# blues
BLUE = "#2563EB"            # primary
BLUE_HOVER = "#1D4ED8"      # primary hover (darker)
BLUE_ACTIVE = "#1E40AF"     # primary pressed
BLUE_LIGHT = "#3B82F6"      # bright accent
BLUE_SOFT = "#60A5FA"       # soft accent / gradient end
BLUE_PALE = "#DBEAFE"       # selection / hover background
BLUE_TINT = "#EFF6FF"       # panel background (very light blue)
# neutrals
BG = "#F8FAFC"              # window background (near-white, cool tint)
BG_PANEL = "#FFFFFF"
BG_LOG = "#F7F9FC"
TEXT = "#0F172A"            # near-black slate
TEXT_MUTED = "#64748B"
TEXT_FAINT = "#94A3B8"
BORDER = "#E2E8F0"
# status colours
SUCCESS = "#10B981"
FAILED = "#EF4444"
SKIPPED = "#94A3B8"
DOWNLOADING = "#3B82F6"
PENDING = "#CBD5E1"

# status tag colours (bg / fg)
SUCCESS_BG = "#ECFDF5"
SUCCESS_FG = "#047857"
FAILED_BG = "#FEF2F2"
FAILED_FG = "#B91C1C"
DOWNLOADING_BG = "#EFF6FF"
DOWNLOADING_FG = "#1D4ED8"
SKIPPED_BG = "#F8FAFC"
SKIPPED_FG = "#94A3B8"
PENDING_BG = "#FFFFFF"
PENDING_FG = "#475569"

# ── fonts (unified type scale, 10pt base for crisp rendering) ───────
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_SMALL_BOLD = ("Microsoft YaHei UI", 9, "bold")
FONT_SECTION = ("Microsoft YaHei UI", 11, "bold")
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_MONO = ("Consolas", 10)

# ── legacy aliases (kept for compatibility with existing imports) ────
DOUYIN_RED = BLUE
DOUYIN_RED_DARK = BLUE_HOVER
BG_LIGHT = BG
TEXT_DARK = TEXT


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Interpolate between two hex colours ``#rrggbb`` at fraction ``t``."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return "#%02x%02x%02x" % (r, g, b)


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Apply the custom tags on top of sv-ttk."""
    style = ttk.Style(root)
    
    # Fonts
    style.configure(".", font=FONT)
    style.configure("Treeview", font=FONT, rowheight=38)
    style.configure("Treeview.Heading", font=FONT_BOLD)

    # primary (blue) action button
    style.configure("Primary.TButton", font=FONT_BOLD)
    # danger (stop) button
    style.configure("Danger.TButton", foreground=FAILED)

    # ── colour-coded row tags ────────────────────────────────────
    style.configure("row_success.Treeview", background=SUCCESS_BG, foreground=SUCCESS_FG)
    style.map("row_success.Treeview", background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    style.configure("row_failed.Treeview", background=FAILED_BG, foreground=FAILED_FG)
    style.map("row_failed.Treeview", background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    style.configure("row_downloading.Treeview", background=DOWNLOADING_BG, foreground=DOWNLOADING_FG)
    style.map("row_downloading.Treeview", background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    style.configure("row_skipped.Treeview", background=SKIPPED_BG, foreground=SKIPPED_FG)
    style.map("row_skipped.Treeview", background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    style.configure("row_pending.Treeview", background=PENDING_BG, foreground=PENDING_FG)
    style.map("row_pending.Treeview", background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])

    return style
