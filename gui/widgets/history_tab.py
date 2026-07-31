"""Download history tab — paginated table of previous downloads."""

import asyncio
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
from pathlib import Path


class HistoryTab(ttk.Frame):
    PAGE_SIZE = 50

    def __init__(self, parent, db_path: str):
        super().__init__(parent, padding=0)
        self.db_path = db_path
        self._page = 1
        self._total = 0
        self._filters: dict = {}

        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # ── filter bar ────────────────────────────────────────────
        bar = ttk.Frame(self, padding=6)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")

        ttk.Label(bar, text="作者").pack(side="left")
        self.author_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.author_var, width=18).pack(side="left", padx=(4, 12))

        ttk.Label(bar, text="类型").pack(side="left")
        self.type_var = tk.StringVar(value="全部")
        ttk.Combobox(bar, textvariable=self.type_var, values=["全部", "视频", "图文", "音乐"],
                     state="readonly", width=8).pack(side="left", padx=(4, 12))

        ttk.Label(bar, text="标题").pack(side="left")
        self.title_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.title_var, width=24).pack(side="left", padx=(4, 12))

        ttk.Button(bar, text="搜索", command=self._search, style="Tool.TButton").pack(side="left")
        ttk.Button(bar, text="刷新", command=self._refresh, style="Tool.TButton").pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="打开所在目录", command=self._open_selected_dir,
                   style="Tool.TButton").pack(side="left", padx=(8, 0))

        # ── treeview ──────────────────────────────────────────────
        columns = ("aweme_id", "title", "author", "type", "create_time", "download_time", "file_path")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="extended")
        headers = {
            "aweme_id": "作品 ID", "title": "名称", "author": "作者",
            "type": "类型", "create_time": "发布时间", "download_time": "下载时间",
            "file_path": "文件路径",
        }
        # Sensible widths: title/file_path absorb extra space; the rest are
        # fixed-size columns. Users can still drag header separators to
        # resize any column — minwidth prevents collapsing them fully.
        widths = {
            "aweme_id": 110, "title": 300, "author": 110,
            "type": 60, "create_time": 140, "download_time": 140, "file_path": 240,
        }
        minwidths = {
            "aweme_id": 80, "title": 140, "author": 80,
            "type": 50, "create_time": 120, "download_time": 120, "file_path": 150,
        }
        stretch_cols = {"title": True, "file_path": True}
        for col in columns:
            self.tree.heading(col, text=headers[col],
                              command=lambda c=col: self._sort_history(c))
            self.tree.column(col, width=widths[col], minwidth=minwidths[col],
                             anchor="w", stretch=stretch_cols.get(col, False))
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        # Zebra stripe tags
        self.tree.tag_configure("even", background="#F8FAFC")
        self.tree.tag_configure("odd", background="#FFFFFF")

        # ── pager ─────────────────────────────────────────────────
        pager = ttk.Frame(self, padding=6)
        pager.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(pager, text="上一页", command=self._prev_page, style="Tool.TButton").pack(side="left")
        ttk.Button(pager, text="下一页", command=self._next_page, style="Tool.TButton").pack(
            side="left", padx=(8, 0))
        self.page_label = ttk.Label(pager, text="第 1 页")
        self.page_label.pack(side="left", padx=(16, 0))

        self._sort_col: str | None = None
        self._sort_rev = False

        # ── right-click menu ─────────────────────────────────────
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label="打开文件所在目录", command=self._open_selected_dir)
        self._ctx_menu.add_command(label="复制作品 ID", command=self._copy_aweme_id)
        self.tree.bind("<Button-3>", self._on_right_click)

    # ── public API ────────────────────────────────────────────────

    def load_page(self):
        """(Re)load current page from DB in a background thread."""
        t = threading.Thread(target=self._load_page_thread, daemon=True)
        t.start()

    # ── internal ──────────────────────────────────────────────────

    def _search(self):
        self._page = 1
        self._filters = {}
        author = self.author_var.get().strip()
        if author:
            self._filters["author"] = author
        aweme_type = self.type_var.get().strip()
        if aweme_type and aweme_type != "全部":
            type_map = {"视频": "video", "图文": "gallery", "音乐": "music"}
            self._filters["aweme_type"] = type_map.get(aweme_type, aweme_type)
        title = self.title_var.get().strip()
        if title:
            self._filters["title"] = title
        self.load_page()

    def _refresh(self):
        self._page = 1
        self._filters = {}
        self.author_var.set("")
        self.type_var.set("全部")
        self.title_var.set("")
        self.load_page()

    def _prev_page(self):
        if self._page > 1:
            self._page -= 1
            self.load_page()

    def _next_page(self):
        max_page = max(1, (self._total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        if self._page < max_page:
            self._page += 1
            self.load_page()

    def _load_page_thread(self):
        try:
            result = asyncio.run(self._query_db())
            self.after(0, self._populate, result)
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror("加载失败", str(exc)))

    async def _query_db(self):
        from storage import Database
        db = Database(self.db_path)
        await db.initialize()
        try:
            result = await db.get_aweme_history(
                page=self._page, size=self.PAGE_SIZE, **self._filters)
        finally:
            await db.close()
        return result

    def _populate(self, result: dict):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._total = result.get("total", 0)
        for idx, row in enumerate(result.get("items", [])):
            tag = "even" if idx % 2 == 0 else "odd"
            self.tree.insert("", "end", values=(
                row.get("aweme_id", ""),
                row.get("title", ""),
                row.get("author_name", ""),
                row.get("aweme_type", ""),
                self._fmt_ts(row.get("create_time")),
                self._fmt_ts(row.get("download_time")),
                row.get("file_path", ""),
            ), tags=(tag,))
        max_page = max(1, (self._total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self.page_label.configure(text=f"第 {self._page} 页 / 共 {max_page} 页  ({self._total} 条)")

    def _sort_history(self, col: str):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False
        items = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children("")]
        try:
            items.sort(key=lambda x: str(x[0]).lower(), reverse=self._sort_rev)
        except Exception:
            items.sort(key=lambda x: str(x[0]), reverse=self._sort_rev)
        for idx, (_val, iid) in enumerate(items):
            self.tree.move(iid, "", idx)

    def _open_selected_dir(self):
        sel = self.tree.selection()
        if not sel:
            return
        values = self.tree.item(sel[0], "values")
        file_path = values[6] if len(values) > 6 else ""
        if file_path:
            p = Path(file_path)
            if p.exists():
                import os
                os.startfile(str(p.parent if p.is_file() else p))
            else:
                messagebox.showinfo("提示", "文件已不存在")

    @staticmethod
    def _fmt_ts(ts) -> str:
        if not ts:
            return ""
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts)

    def _on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self._ctx_menu.post(event.x_root, event.y_root)

    def _copy_aweme_id(self):
        sel = self.tree.selection()
        if sel:
            values = self.tree.item(sel[0], "values")
            if values:
                self.clipboard_clear()
                self.clipboard_append(str(values[0]))
