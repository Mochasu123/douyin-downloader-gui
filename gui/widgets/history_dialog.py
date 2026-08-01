"""历史链接 / 历史用户对话框。

链接历史：表格（时间 / 链接 / 名称），单选，双击填入；
用户历史：卡片（头像 + 用户名），双击填入。
两个对话框都支持删除选中与清空。
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from gui.theme import BLUE, BORDER, FONT, FONT_SMALL, TEXT_MUTED
from gui.widgets.rounded_button import RoundedButton


class _HistoryBase(tk.Toplevel):
    def __init__(self, parent, title, size):
        super().__init__(parent)
        self.title(title)
        self.geometry(size)
        self.configure(bg="#FFFFFF")
        self.transient(parent)
        self._rows: list[dict] = []

    # ── helpers ─────────────────────────────────────────────────────

    def _confirm(self, text: str) -> bool:
        return messagebox.askyesno("确认", text, parent=self)

    def _reload(self):
        """由子类实现：重新拉取数据并刷新列表。"""
        raise NotImplementedError


class LinkHistoryDialog(_HistoryBase):
    """成功解析过的链接历史：时间 / 链接 / 名称。"""

    def __init__(self, parent, rows, on_pick, fetch_rows, on_delete, on_clear):
        super().__init__(parent, "历史链接（仅成功解析过的）", "780x440")
        self.on_pick = on_pick
        self._fetch_rows = fetch_rows
        self._on_delete = on_delete
        self._on_clear = on_clear
        self._rows = rows
        self._iid_to_row: dict[str, dict] = {}

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        columns = ("time", "url", "name")
        headers = {"time": "时间", "url": "链接", "name": "解析后的名称"}
        widths = {"time": 130, "url": 360, "name": 220}
        self.tree = ttk.Treeview(self, columns=columns, show="headings",
                                 selectmode="browse")
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], anchor="w",
                             stretch=(col != "time"), minwidth=50)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=(10, 4))
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-Button-1>", lambda _e: self._pick_selected())

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text="双击或选中后点「使用」填入链接；每链接只记录首次成功解析",
                  font=FONT_SMALL, foreground=TEXT_MUTED).grid(row=0, column=0, sticky="w")
        RoundedButton(bar, text="清空", style="ghost", height=28,
                      command=self._clear_all).grid(row=0, column=3, padx=(6, 0))
        RoundedButton(bar, text="删除选中", style="ghost", height=28,
                      command=self._delete_selected).grid(row=0, column=2, padx=(6, 0))
        RoundedButton(bar, text="使用", style="primary", height=28,
                      command=self._pick_selected).grid(row=0, column=1, padx=(6, 0))

        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._iid_to_row.clear()
        for index, row in enumerate(self._rows):
            iid = f"row_{index}"
            self._iid_to_row[iid] = row
            self.tree.insert(
                "", "end", iid=iid,
                values=(row.get("created_at") or "",
                        row.get("original_url") or "",
                        row.get("name") or ""),
            )

    def _pick_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        row = self._iid_to_row.get(selection[0])
        if row:
            self.on_pick(str(row.get("original_url") or ""))

    def _delete_selected(self):
        selection = self.tree.selection()
        if not selection:
            return
        if not self._confirm("删除选中的历史记录？"):
            return
        ids = [int(self._iid_to_row[iid]["id"]) for iid in selection]
        self._on_delete(ids)
        self._rows = self._fetch_rows()
        self._refresh()

    def _clear_all(self):
        if not self._rows:
            return
        if not self._confirm("清空全部历史链接？此操作不可恢复。"):
            return
        self._on_clear()
        self._rows = self._fetch_rows()
        self._refresh()


class UserHistoryDialog(_HistoryBase):
    """历史用户：头像 + 用户名卡片，双击填入链接。"""

    _CARD_W = 170
    _CARD_H = 100
    _COLS = 3

    def __init__(self, parent, rows, avatar_dir, on_pick, fetch_rows,
                 on_delete, on_clear):
        super().__init__(parent, "历史用户", "720x460")
        self.on_pick = on_pick
        self.avatar_dir = Path(avatar_dir)
        self._fetch_rows = fetch_rows
        self._on_delete = on_delete
        self._on_clear = on_clear
        self._rows = rows
        self._cards: dict[str, dict] = {}
        self._selected: set[str] = set()
        self._photos: list = []

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, bg="#FFFFFF", highlightthickness=0)
        self._canvas.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        scroll = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=(10, 4))
        self._canvas.configure(yscrollcommand=scroll.set)
        self._grid_frame = tk.Frame(self._canvas, bg="#FFFFFF")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._grid_frame, anchor="nw")
        self._grid_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfigure(
                              self._canvas_window, width=e.width))
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 10))
        bar.columnconfigure(0, weight=1)
        ttk.Label(bar, text="双击用户卡片填入链接；头像在首次解析时缓存到本地",
                  font=FONT_SMALL, foreground=TEXT_MUTED).grid(row=0, column=0, sticky="w")
        RoundedButton(bar, text="清空", style="ghost", height=28,
                      command=self._clear_all).grid(row=0, column=3, padx=(6, 0))
        RoundedButton(bar, text="删除选中", style="ghost", height=28,
                      command=self._delete_selected).grid(row=0, column=2, padx=(6, 0))

        self._refresh()

    # ── cards ───────────────────────────────────────────────────────

    def _refresh(self):
        for child in self._grid_frame.winfo_children():
            child.destroy()
        self._cards.clear()
        self._selected.clear()
        self._photos.clear()
        for index, row in enumerate(self._rows):
            key = f"user_{index}"
            card = tk.Frame(self._grid_frame, width=self._CARD_W,
                            height=self._CARD_H, bg="#FFFFFF",
                            highlightthickness=2, highlightbackground=BORDER)
            card.pack_propagate(False)
            photo = self._avatar_photo(row)
            avatar = tk.Label(card, image=photo or "", bg="#FFFFFF",
                              width=56, height=56)
            avatar.pack(pady=(10, 2))
            name = tk.Label(card, text=(row.get("name") or "未知")[:12],
                            font=FONT_SMALL, fg="#0F172A", bg="#FFFFFF")
            name.pack()
            time_label = tk.Label(card, text=row.get("created_at") or "",
                                  font=("Microsoft YaHei UI", 8),
                                  fg=TEXT_MUTED, bg="#FFFFFF")
            time_label.pack()
            self._photos.append(photo)
            self._cards[key] = {
                "frame": card, "row": row, "selected": False,
            }
            for widget in (card, avatar, name, time_label):
                widget.bind("<Button-1>", lambda _e, k=key: self._toggle(k))
            card.bind("<Double-Button-1>", lambda _e, k=key: self._pick(k))
            avatar.bind("<Double-Button-1>", lambda _e, k=key: self._pick(k))
            name.bind("<Double-Button-1>", lambda _e, k=key: self._pick(k))
            row_idx = index // self._COLS
            col_idx = index % self._COLS
            card.grid(row=row_idx, column=col_idx, padx=6, pady=6, sticky="nw")

    def _avatar_photo(self, row):
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageTk

            cache = self.avatar_dir / f"{row.get('content_id') or ''}.jpg"
            if cache.exists():
                image = Image.open(cache).convert("RGB")
            else:
                image = Image.new("RGB", (56, 56), (219, 234, 254))
                draw = ImageDraw.Draw(image)
                initial = (row.get("name") or "?")[:1]
                try:
                    font = ImageFont.truetype(
                        "C:/Windows/Fonts/msyh.ttc", 28)
                except Exception:
                    font = ImageFont.load_default()
                draw.text((28, 28), initial, fill="#2563EB",
                          font=font, anchor="mm")
            image.thumbnail((56, 56))
            return ImageTk.PhotoImage(image)
        except Exception:
            return None

    def _toggle(self, key: str):
        card = self._cards.get(key)
        if not card:
            return
        if key in self._selected:
            self._selected.discard(key)
            card["selected"] = False
            card["frame"].configure(highlightbackground=BORDER)
        else:
            self._selected.clear()
            for k, c in self._cards.items():
                c["selected"] = False
                c["frame"].configure(highlightbackground=BORDER)
            self._selected.add(key)
            card["selected"] = True
            card["frame"].configure(highlightbackground=BLUE)

    def _pick(self, key: str):
        card = self._cards.get(key)
        if card:
            self.on_pick(str(card["row"].get("original_url") or ""))

    def _delete_selected(self):
        if not self._selected:
            return
        if not self._confirm("删除选中的历史用户？"):
            return
        ids = [int(self._cards[key]["row"]["id"]) for key in self._selected]
        self._on_delete(ids)
        self._rows = self._fetch_rows()
        self._refresh()

    def _clear_all(self):
        if not self._rows:
            return
        if not self._confirm("清空全部历史用户？此操作不可恢复。"):
            return
        self._on_clear()
        self._rows = self._fetch_rows()
        self._refresh()

    def _on_mousewheel(self, event):
        widget = self._canvas.winfo_containing(event.x_root, event.y_root)
        while widget is not None and widget != self._canvas:
            widget = widget.master
        if widget == self._canvas:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")
