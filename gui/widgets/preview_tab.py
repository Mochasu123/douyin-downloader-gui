"""Preview tab — Treeview table with collection grouping & filter."""

import tkinter as tk
from tkinter import ttk


class PreviewTab(ttk.Frame):
    STATUS_TAGS = {
        "待下载": "row_pending",
        "正在下载": "row_downloading",
        "已下载到本地": "row_success",
        "已存在": "row_skipped",
        "失败": "row_failed",
        "已终止": "row_failed",
        "暂不支持": "row_skipped",
    }

    def __init__(self, parent, on_collection_filter=None):
        super().__init__(parent, padding=0)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self._aweme_id_to_iid: dict[str, str] = {}
        self._sort_column: str | None = None
        self._sort_reverse: bool = False
        self._on_collection_filter = on_collection_filter
        self._collections: list[str] = []
        self._current_filter: str = "全部"

        # ── Filter bar ───────────────────────────────────────────
        self.filter_bar = ttk.Frame(self)
        self.filter_bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))

        ttk.Label(self.filter_bar, text="筛选:").pack(side="left")
        self.filter_combo = ttk.Combobox(self.filter_bar, values=["全部"], state="readonly", width=18)
        self.filter_combo.pack(side="left", padx=(6, 12))
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)
        self.filter_combo.set("全部")

        self.select_all_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.filter_bar, text="全选", variable=self.select_all_var,
                       command=self._on_select_all_toggle,
                       relief="flat", bg="#F5F5F5", activebackground="#F5F5F5",
                       selectcolor="#F5F5F5").pack(side="left")

        self.filter_count = ttk.Label(self.filter_bar, text="", foreground="#888",
                                       font=("Microsoft YaHei UI", 8))
        self.filter_count.pack(side="left", padx=(12, 0))

        # ── Treeview ─────────────────────────────────────────────
        columns = ("index", "title", "collection", "publish_time", "duration", "media_type", "size", "status", "aweme_id")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="extended")

        headers = {
            "index": "#", "title": "名称", "collection": "合集",
            "publish_time": "发布时间", "duration": "时长",
            "media_type": "类型", "size": "大小",
            "status": "状态", "aweme_id": "作品 ID",
        }
        widths = {
            "index": 45, "title": 300, "collection": 80,
            "publish_time": 150, "duration": 65,
            "media_type": 55, "size": 70, "status": 105, "aweme_id": 0,
        }
        for col in columns:
            self.tree.heading(col, text=headers[col],
                              command=lambda c=col: self._sort_by_column(c))
            self.tree.column(col, width=widths[col], anchor="w", minwidth=30,
                             stretch=(col == "title"))
        self.tree.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        # Hide aweme_id column (used for data but not display)
        self.tree.column("aweme_id", width=0, stretch=False)

        for status, tag in self.STATUS_TAGS.items():
            self.tree.tag_configure(tag)

        # ── Right-click menu ─────────────────────────────────────
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._ctx_menu.add_command(label="全选此合集", command=self._select_this_collection)
        self._ctx_menu.add_command(label="复制作品 ID", command=self._copy_aweme_id)
        self.tree.bind("<Button-3>", self._on_right_click)

    # ── public API ──────────────────────────────────────────────────

    def set_collections(self, collections: list[str]):
        """Update the filter dropdown with discovered collections."""
        self._collections = collections
        values = ["全部"]
        for c in collections:
            label = f"{c} ({self._count_collection(c)})"
            values.append(label)
        self.filter_combo["values"] = values

    def _count_collection(self, name: str) -> int:
        count = 0
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if len(vals) >= 3 and str(vals[2]) == name:
                count += 1
        return count

    def refresh_collection_counts(self):
        """Update collection counts in filter dropdown after items change."""
        values = ["全部"]
        for c in self._collections:
            count = self._count_collection(c)
            label = f"{c} ({count})"
            values.append(label)
        self.filter_combo["values"] = values
        self._update_filter_count()

    def add_item(self, item, index: int):
        iid = f"row_{index}"
        title = getattr(item, "title", "无标题") or "无标题"
        if len(title) > 50:
            title = title[:47] + "..."
        collection = getattr(item, "collection_name", "") or "-"
        values = (
            index, title, collection,
            getattr(item, "publish_time", "未知"),
            getattr(item, "duration", "未知"),
            getattr(item, "media_type", "未知"),
            getattr(item, "size_text", "未知"),
            "待下载",
            getattr(item, "aweme_id", ""),
        )
        self.tree.insert("", "end", iid=iid, values=values, tags=("row_pending",))
        aweme_id = str(values[8])
        self._aweme_id_to_iid[aweme_id] = iid

    def update_status(self, aweme_id: str, status: str, size_text: str | None = None):
        iid = self._aweme_id_to_iid.get(str(aweme_id))
        if iid is None:
            return
        try:
            values = list(self.tree.item(iid, "values"))
        except Exception:
            return
        if len(values) < 9:
            return
        values[7] = status
        if size_text:
            values[6] = size_text
        tag = self.STATUS_TAGS.get(status, "row_pending")
        self.tree.item(iid, values=values, tags=(tag,))
        self.tree.see(iid)

    def clear(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self._aweme_id_to_iid.clear()
        self._collections = []
        self.filter_combo["values"] = ["全部"]
        self.filter_combo.set("全部")
        self.filter_count.configure(text="")

    def get_selected_iids(self) -> list[str]:
        return list(self.tree.selection())

    def get_visible_iids(self) -> list[str]:
        return list(self.tree.get_children())

    def select_all_visible(self):
        self.tree.selection_set(self.get_visible_iids())

    def clear_selection(self):
        self.tree.selection_remove(self.tree.selection())

    # ── filter ──────────────────────────────────────────────────────

    def _on_filter_changed(self, _event=None):
        selected = self.filter_combo.get()
        # Extract base collection name (strip count)
        base = selected.split(" (")[0] if " (" in selected else selected
        self._current_filter = base
        self._apply_filter()
        self._update_filter_count()

    def _apply_filter(self):
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if self._current_filter == "全部":
                self.tree.reattach(iid, "", "end")
            elif len(vals) >= 3 and str(vals[2]) == self._current_filter:
                self.tree.reattach(iid, "", "end")
            else:
                self.tree.detach(iid)
        if self.select_all_var.get():
            self.select_all_visible()

    def _update_filter_count(self):
        visible = len(self.get_visible_iids())
        total = len(self._aweme_id_to_iid)
        self.filter_count.configure(
            text=f"显示 {visible} / 共 {total} 个作品" if self._current_filter != "全部"
            else f"共 {total} 个作品")

    def _on_select_all_toggle(self):
        if self.select_all_var.get():
            self.select_all_visible()
        else:
            self.clear_selection()

    # ── sorting ─────────────────────────────────────────────────────

    def _sort_by_column(self, col: str):
        if self._sort_column == col:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = col
            self._sort_reverse = False

        col_idx = {
            "index": 0, "title": 1, "collection": 2, "publish_time": 3,
            "duration": 4, "media_type": 5, "size": 6, "status": 7,
        }.get(col, 0)

        items = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children("")]
        try:
            items.sort(key=lambda x: (x[0] == "", str(x[0]).lower()), reverse=self._sort_reverse)
        except Exception:
            items.sort(key=lambda x: str(x[0]), reverse=self._sort_reverse)
        for idx, (_val, iid) in enumerate(items):
            self.tree.move(iid, "", idx)

    # ── right-click ─────────────────────────────────────────────────

    def _on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self._ctx_menu.post(event.x_root, event.y_root)

    def _select_this_collection(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if len(vals) < 3:
            return
        collection = str(vals[2])
        to_select = []
        for iid in self.get_visible_iids():
            v = self.tree.item(iid, "values")
            if len(v) >= 3 and str(v[2]) == collection:
                to_select.append(iid)
        self.tree.selection_set(to_select)

    def _copy_aweme_id(self):
        sel = self.tree.selection()
        if sel:
            values = self.tree.item(sel[0], "values")
            if len(values) >= 9:
                self.clipboard_clear()
                self.clipboard_append(str(values[8]))
