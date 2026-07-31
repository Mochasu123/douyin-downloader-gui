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
    """Apply the blue/white theme and return the style object."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    style.theme_use("clam")

    # ── global defaults ───────────────────────────────────────────
    style.configure(".", background=BG, foreground=TEXT, font=FONT)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Card.TFrame", background=BG_PANEL)
    style.configure("Card.TLabel", background=BG_PANEL, foreground=TEXT)
    style.configure("LogPanel.TFrame", background=BG_PANEL)

    # ── buttons ───────────────────────────────────────────────────
    style.configure("TButton", padding=(14, 6), relief="flat", borderwidth=0)
    style.map("TButton",
              background=[("active", BLUE_PALE), ("!active", BG_PANEL)],
              foreground=[("active", BLUE), ("!active", BLUE)],
              focuscolor=[("focus", BLUE)])

    # primary (blue) action button — light blue fill, blue text
    style.configure("Primary.TButton", background=BLUE_PALE, foreground="#1D4ED8",
                    font=FONT_BOLD)
    style.map("Primary.TButton",
              background=[("active", "#BFDBFE"), ("pressed", "#93C5FD"),
                          ("disabled", "#E2E8F0")],
              foreground=[("active", "#1D4ED8"), ("pressed", "#1D4ED8"),
                          ("disabled", "#94A3B8")])

    # danger (stop) button — subtle red text on white
    style.configure("Danger.TButton", background=BG_PANEL, foreground=FAILED)
    style.map("Danger.TButton",
              background=[("active", FAILED_BG), ("pressed", "#FEE2E2"),
                          ("disabled", "#E2E8F0")],
              foreground=[("active", FAILED), ("pressed", FAILED),
                          ("disabled", "#94A3B8")])

    # tool button (secondary action)
    style.configure("Tool.TButton", padding=(8, 4), background=BG_PANEL,
                    foreground=TEXT_MUTED)
    style.map("Tool.TButton",
              background=[("active", BLUE_TINT), ("!active", BG_PANEL)],
              foreground=[("active", BLUE), ("!active", TEXT_MUTED)])

    # ── progress bar (kept for ttk fallbacks; GUI uses SmoothProgressBar) ──
    style.configure("TProgressbar", troughcolor=BORDER, background=BLUE,
                    thickness=10)

    # ── checkbutton ───────────────────────────────────────────────
    # tk.Checkbutton is used for correct ✓ indicator (see widgets); the
    # ttk style here only covers any stray ttk checkboxes.
    style.configure("TCheckbutton", background=BG, foreground=TEXT)

    # ── entry / combobox / spinbox ────────────────────────────────
    style.configure("TEntry", fieldbackground=BG_PANEL, bordercolor=BORDER,
                    borderwidth=1, relief="solid", padding=2)
    style.map("TEntry", bordercolor=[("focus", BLUE)], fieldbackground=[("disabled", "#F1F5F9")])
    style.configure("TCombobox", fieldbackground=BG_PANEL, bordercolor=BORDER,
                    borderwidth=1, relief="solid", padding=2, arrowcolor=TEXT_MUTED)
    style.map("TCombobox",
              fieldbackground=[("readonly", BG_PANEL), ("disabled", "#F1F5F9")],
              bordercolor=[("focus", BLUE)])
    style.configure("TSpinbox", fieldbackground=BG_PANEL, bordercolor=BORDER,
                    borderwidth=1, relief="solid", padding=2)
    style.map("TSpinbox", bordercolor=[("focus", BLUE)])

    # ── notebook (tabs) ───────────────────────────────────────────
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(20, 9), font=FONT, borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", BG_PANEL), ("!selected", BG)],
              foreground=[("selected", BLUE), ("!selected", TEXT_MUTED)],
              focuscolor=[("selected", BG_PANEL)])

    # ── treeview (preview / history tables) ───────────────────────
    style.configure("Treeview", font=FONT, rowheight=38,
                    fieldbackground=BG_PANEL, background=BG_PANEL,
                    foreground=TEXT, bordercolor=BORDER)
    style.map("Treeview",
              background=[("selected", BLUE)],
              foreground=[("selected", "#FFFFFF")])
    style.configure("Treeview.Heading", font=FONT_BOLD,
                    background="#F8FAFC", foreground=TEXT_MUTED, relief="flat",
                    padding=(10, 7))
    style.map("Treeview.Heading", background=[("active", "#EEF2F7")])

    # ── colour-coded row tags ────────────────────────────────────
    # Success  – green
    style.configure("row_success.Treeview", background=SUCCESS_BG, foreground=SUCCESS_FG)
    style.map("row_success.Treeview",
              background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    # Failed   – red
    style.configure("row_failed.Treeview", background=FAILED_BG, foreground=FAILED_FG)
    style.map("row_failed.Treeview",
              background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    # Downloading – blue
    style.configure("row_downloading.Treeview", background=DOWNLOADING_BG,
                    foreground=DOWNLOADING_FG)
    style.map("row_downloading.Treeview",
              background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    # Skipped – grey
    style.configure("row_skipped.Treeview", background=SKIPPED_BG, foreground=SKIPPED_FG)
    style.map("row_skipped.Treeview",
              background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])
    # Pending – white (default)
    style.configure("row_pending.Treeview", background=PENDING_BG, foreground=PENDING_FG)
    style.map("row_pending.Treeview",
              background=[("selected", BLUE)], foreground=[("selected", "#FFFFFF")])

    # ── scrollbar / separator ─────────────────────────────────────
    style.configure("TScrollbar", background="#CBD5E1", troughcolor=BLUE_TINT,
                    bordercolor=BLUE_TINT, arrowcolor=TEXT_MUTED, relief="flat")
    style.map("TScrollbar", background=[("active", BLUE_SOFT)])
    style.configure("TSeparator", background=BORDER)

    return style
