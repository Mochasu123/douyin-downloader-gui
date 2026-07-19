"""ttk theme and styling for Douyin Downloader GUI.

Applies a modern ``clam``-based theme with Douyin-red accents,
colour-coded Treeview status tags, and improved spacing.
"""

from tkinter import ttk
import tkinter as tk

# ── palette ──────────────────────────────────────────────────────────
DOUYIN_RED = "#FE2C55"
DOUYIN_RED_DARK = "#E0244A"
BG_LIGHT = "#F5F5F5"
TEXT_DARK = "#1A1A1A"
TEXT_MUTED = "#888888"
BORDER = "#D0D0D0"
SUCCESS_BG = "#E8F5E9"
SUCCESS_FG = "#2E7D32"
FAILED_BG = "#FFEBEE"
FAILED_FG = "#C62828"
DOWNLOADING_BG = "#E3F2FD"
DOWNLOADING_FG = "#1565C0"
SKIPPED_BG = "#F5F5F5"
SKIPPED_FG = "#9E9E9E"
PENDING_BG = "#FFFFFF"
PENDING_FG = "#616161"


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Apply the Douyin-branded theme and return the style object."""
    style = ttk.Style(root)
    style.theme_use("clam")

    # ── global defaults ───────────────────────────────────────────
    style.configure(".", background=BG_LIGHT, foreground=TEXT_DARK, font=("Microsoft YaHei UI", 9))
    style.configure("TFrame", background=BG_LIGHT)
    style.configure("TLabel", background=BG_LIGHT, foreground=TEXT_DARK)
    style.configure("TButton", padding=(12, 5), relief="flat")
    style.map("TButton",
              background=[("active", DOUYIN_RED), ("!active", "#E0E0E0")],
              foreground=[("active", "#FFFFFF"), ("!active", TEXT_DARK)])

    # ── primary (red) action button ───────────────────────────────
    style.configure("Primary.TButton", background=DOUYIN_RED, foreground="#FFFFFF",
                    font=("Microsoft YaHei UI", 9, "bold"))
    style.map("Primary.TButton",
              background=[("active", DOUYIN_RED_DARK), ("disabled", "#CCCCCC")],
              foreground=[("active", "#FFFFFF"), ("disabled", "#999999")])

    # ── danger (stop) button ──────────────────────────────────────
    style.configure("Danger.TButton", background="#EF5350", foreground="#FFFFFF")
    style.map("Danger.TButton",
              background=[("active", "#D32F2F"), ("disabled", "#CCCCCC")],
              foreground=[("active", "#FFFFFF"), ("disabled", "#999999")])

    # ── tool button (secondary action) ────────────────────────────
    style.configure("Tool.TButton", padding=(8, 4))

    # ── progress bar ──────────────────────────────────────────────
    style.configure("TProgressbar", troughcolor="#E0E0E0", background=DOUYIN_RED,
                    thickness=10)

    # ── checkbutton (tk native for correct ✓ indicator) ────────
    # ttk.Checkbutton uses clam theme's × indicator on Windows;
    # tk.Checkbutton always shows proper ✓/☐ on all platforms.
    # Per-widget styling is applied inline (bg=..., relief="flat").

    # ── entry / combobox / spinbox ────────────────────────────────
    style.configure("TEntry", fieldbackground="#FFFFFF", borderwidth=1, relief="solid")
    style.configure("TCombobox", fieldbackground="#FFFFFF", borderwidth=1, relief="solid")

    # ── notebook (tabs) ───────────────────────────────────────────
    style.configure("TNotebook", background=BG_LIGHT, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(16, 6), font=("Microsoft YaHei UI", 9))
    style.map("TNotebook.Tab",
              background=[("selected", "#FFFFFF"), ("!selected", BG_LIGHT)],
              foreground=[("selected", DOUYIN_RED), ("!selected", TEXT_DARK)])

    # ── treeview (preview / history tables) ───────────────────────
    style.configure("Treeview", font=("Microsoft YaHei UI", 9), rowheight=32,
                    fieldbackground="#FFFFFF")
    style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"),
                    background="#EEEEEE", foreground=TEXT_DARK, relief="flat",
                    padding=(6, 4))
    style.map("Treeview.Heading", background=[("active", "#E0E0E0")])

    # ── colour-coded row tags ────────────────────────────────────
    style.configure("Treeview", background="#FFFFFF", foreground=TEXT_DARK)

    # Success  – green
    style.configure("row_success.Treeview", background=SUCCESS_BG, foreground=SUCCESS_FG)
    style.map("row_success.Treeview",
              background=[("selected", DOUYIN_RED)],
              foreground=[("selected", "#FFFFFF")])

    # Failed   – red
    style.configure("row_failed.Treeview", background=FAILED_BG, foreground=FAILED_FG)
    style.map("row_failed.Treeview",
              background=[("selected", DOUYIN_RED)],
              foreground=[("selected", "#FFFFFF")])

    # Downloading – blue
    style.configure("row_downloading.Treeview", background=DOWNLOADING_BG,
                    foreground=DOWNLOADING_FG)
    style.map("row_downloading.Treeview",
              background=[("selected", DOUYIN_RED)],
              foreground=[("selected", "#FFFFFF")])

    # Skipped – grey
    style.configure("row_skipped.Treeview", background=SKIPPED_BG, foreground=SKIPPED_FG)
    style.map("row_skipped.Treeview",
              background=[("selected", DOUYIN_RED)],
              foreground=[("selected", "#FFFFFF")])

    # Pending – white (default)
    style.configure("row_pending.Treeview", background=PENDING_BG, foreground=PENDING_FG)
    style.map("row_pending.Treeview",
              background=[("selected", DOUYIN_RED)],
              foreground=[("selected", "#FFFFFF")])

    return style
