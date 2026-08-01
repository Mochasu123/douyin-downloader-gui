"""评论浏览页签 — 评论卡片列表 + 图片网格预览/选中下载。

- 左侧：评论卡片（发送人/时间/属地/点赞/全文），图片评论显示缩略图；
  双击卡片跳转到右侧对应图片并滚动到可见位置。
- 右侧：评论图片缩略图网格，单击放大预览，双击勾选下载（也可用右上角
  复选框），动图自动合并。
- 底部：保存目录、下载选中、导出 Excel。
"""

from __future__ import annotations

import tkinter as tk
from bisect import bisect_right
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.theme import BLUE, BORDER, FONT, FONT_BOLD, FONT_SMALL, TEXT_MUTED
from gui.widgets.emoji_text import EmojiText
from gui.widgets.rounded_button import RoundedButton

_CELL_WIDTH = 116
_CELL_HEIGHT = 136
_GRID_COLUMNS = 4
_CARD_WRAP = 330


class CommentsTab(ttk.Frame):
    def __init__(self, parent, on_load, on_download, on_zoom, on_open_dir):
        super().__init__(parent, padding=10)
        self.on_load = on_load
        self.on_download = on_download
        self.on_zoom = on_zoom
        self.on_open_dir = on_open_dir

        self._aweme_id: str = ""
        self._author: str = ""
        self._title: str = ""
        self._comments: dict[str, dict] = {}
        self._card_thumbs: dict[str, dict] = {}
        self._cell_keys: list[str] = []
        self._cells: dict[str, dict] = {}
        self._selected: set[str] = set()
        self._highlight_key: str = ""
        self._busy = False
        self._zoom_window: tk.Toplevel | None = None
        self._card_photos: list = []
        self._cell_photos: list = []
        self._comment_order: list[str] = []
        self._visible_cids: list[str] = []
        self._card_heights: dict[str, int] = {}
        self._thumb_photo_by_cid: dict[str, object] = {}
        self._rendered_cards: dict[str, tk.Frame] = {}
        self._card_refresh_job = None
        self._filter_query = ""
        self._filter_field = "全部"

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Row 0: header ─────────────────────────────────────────
        hdr = ttk.Frame(self)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        hdr.columnconfigure(1, weight=1)
        self.title_label = ttk.Label(hdr, text="作品：—", font=FONT,
                                     foreground=TEXT_MUTED)
        self.title_label.grid(row=0, column=0, sticky="w")
        self.info_label = ttk.Label(hdr, text="", font=FONT_SMALL,
                                    foreground=TEXT_MUTED)
        self.info_label.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self.load_btn = RoundedButton(hdr, text="加载评论", style="primary",
                                      command=on_load, state="disabled")
        self.load_btn.grid(row=0, column=2, sticky="e")

        # ── Row 1: comment cards + image grid ─────────────────────
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew")

        left = ttk.Frame(paned)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        left_hdr = ttk.Frame(left)
        left_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        left_hdr.columnconfigure(1, weight=1)
        self.filter_entry = ttk.Entry(left_hdr, width=16)
        self.filter_entry.grid(row=0, column=0, sticky="w")
        self.filter_entry.bind("<KeyRelease>", self._on_filter_typed)
        self.filter_field_var = tk.StringVar(value="全部")
        self.filter_combo = ttk.Combobox(
            left_hdr, textvariable=self.filter_field_var,
            values=("全部", "发送人", "时间", "IP属地", "点赞", "评论内容"),
            state="readonly", width=8)
        self.filter_combo.grid(row=0, column=1, sticky="w", padx=(6, 0))
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_typed)
        self.comment_count = ttk.Label(left_hdr, text="评论：0", font=FONT,
                                       foreground=TEXT_MUTED)
        self.comment_count.grid(row=0, column=2, sticky="e")

        self._card_canvas = tk.Canvas(left, bg="#FFFFFF", highlightthickness=0)
        self._card_canvas.grid(row=1, column=0, sticky="nsew")
        card_scroll = ttk.Scrollbar(left, orient="vertical",
                                    command=self._scroll_cards)
        card_scroll.grid(row=1, column=1, sticky="ns")
        self._card_canvas.configure(yscrollcommand=card_scroll.set)
        self._card_frame = tk.Frame(self._card_canvas, bg="#FFFFFF")
        self._card_window = self._card_canvas.create_window(
            (0, 0), window=self._card_frame, anchor="nw")
        self._card_frame.bind(
            "<Configure>",
            lambda _e: self._card_canvas.configure(
                scrollregion=self._card_canvas.bbox("all")))
        self._card_canvas.bind("<Configure>", self._on_card_canvas_resize)
        self._card_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        paned.add(left, weight=2)

        right = ttk.Frame(paned, padding=(8, 0, 0, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)
        grid_bar = ttk.Frame(right)
        grid_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.grid_count = ttk.Label(grid_bar, text="评论图片：0", font=FONT,
                                    foreground=TEXT_MUTED)
        self.grid_count.pack(side="left")
        RoundedButton(grid_bar, text="全选", style="ghost", height=26,
                      command=self._select_all).pack(side="right", padx=(4, 0))
        RoundedButton(grid_bar, text="清空", style="ghost", height=26,
                      command=self._clear_selection).pack(side="right", padx=(4, 0))

        self._canvas = tk.Canvas(right, bg="#FFFFFF", highlightthickness=0)
        self._canvas.grid(row=1, column=0, sticky="nsew")
        vscroll = ttk.Scrollbar(right, orient="vertical",
                                command=self._canvas.yview)
        vscroll.grid(row=1, column=1, sticky="ns")
        self._canvas.configure(yscrollcommand=vscroll.set)
        self._grid_frame = tk.Frame(self._canvas, bg="#FFFFFF")
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._grid_frame, anchor="nw")
        self._grid_frame.bind(
            "<Configure>",
            lambda _e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        paned.add(right, weight=3)

        # ── Row 2: save dir + download + export ───────────────────
        bar = ttk.Frame(self)
        bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="保存到", font=FONT_SMALL).grid(row=0, column=0, sticky="w")
        self.save_dir_var = tk.StringVar()
        self.save_dir_entry = ttk.Entry(bar, textvariable=self.save_dir_var)
        self.save_dir_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        RoundedButton(bar, text="打开目录", style="ghost", height=28,
                      command=on_open_dir).grid(row=0, column=2, padx=(0, 6))
        self.export_btn = RoundedButton(bar, text="导出 Excel", style="ghost",
                                        height=28, command=self._on_export,
                                        state="disabled")
        self.export_btn.grid(row=0, column=3, padx=(0, 6))
        self.dl_btn = RoundedButton(bar, text="下载选中图片(0)", style="primary",
                                    command=self._on_download, state="disabled")
        self.dl_btn.grid(row=0, column=4)

        self.status_label = ttk.Label(self, text="加载评论后可预览并勾选下载图片",
                                      font=FONT_SMALL, foreground=TEXT_MUTED)
        self.status_label.grid(row=3, column=0, sticky="w", pady=(4, 0))

    # ── public API ─────────────────────────────────────────────────

    def set_aweme(self, aweme_id: str, title: str, author: str,
                  default_save_dir: str):
        self._aweme_id = str(aweme_id or "")
        self._author = author or ""
        self._title = title or ""
        self.title_label.configure(text=f"作品：{self._title[:60]}")
        self.info_label.configure(
            text=f"作者：{self._author} · ID：{self._aweme_id}")
        self.load_btn.configure(state="normal" if self._aweme_id and not self._busy
                                else "disabled")
        if default_save_dir:
            self.save_dir_var.set(default_save_dir)
        self.status_label.configure(text="点击「加载评论」开始浏览评论与图片")

    def reset(self):
        self._aweme_id = ""
        self._author = ""
        self._title = ""
        self._comments.clear()
        self._card_thumbs.clear()
        self._card_photos.clear()
        self._comment_order.clear()
        self._visible_cids.clear()
        self._card_heights.clear()
        self._thumb_photo_by_cid.clear()
        self._rendered_cards.clear()
        self._cancel_card_refresh()
        for child in self._card_frame.winfo_children():
            child.destroy()
        self._card_frame.configure(height=1)
        self._card_canvas.configure(scrollregion=(0, 0, 1, 1))
        self.filter_entry.delete(0, "end")
        self.filter_field_var.set("全部")
        self._filter_query = ""
        self._filter_field = "全部"
        self._clear_grid()
        self.title_label.configure(text="作品：—")
        self.info_label.configure(text="")
        self.comment_count.configure(text="评论：0")
        self.load_btn.configure(state="disabled")
        self.dl_btn.configure(state="disabled", text="下载选中图片(0)")
        self.export_btn.configure(state="disabled")
        self.status_label.configure(text="在「链接下载」解析单个作品后可查看评论")

    def add_comment(self, display: dict):
        cid = str(display.get("cid") or "")
        if not cid:
            # 个别评论可能缺少 ID，生成兜底 ID 保证不丢评论
            cid = f"no_cid_{len(self._comment_order)}"
        self._comments[cid] = dict(display)
        if cid not in self._comment_order:
            self._comment_order.append(cid)
        self._apply_filter()

    def add_image(self, comment_id: str, index: int, thumb_path, is_live: bool,
                  nickname: str):
        key = f"{comment_id}_{index}"
        if key in self._cells:
            return
        photo = self._load_thumb(thumb_path)
        self._cell_photos.append(photo)
        if photo is not None:
            self._thumb_photo_by_cid[str(comment_id)] = photo

        cell = tk.Frame(self._grid_frame, width=_CELL_WIDTH, height=_CELL_HEIGHT,
                        bg="#FFFFFF", highlightthickness=2,
                        highlightbackground=BORDER)
        cell.pack_propagate(False)
        img_label = tk.Label(cell, image=photo or "", bg="#FFFFFF",
                             width=_CELL_WIDTH - 8, height=_CELL_HEIGHT - 56)
        img_label.pack(pady=(4, 0))
        comment = self._comments.get(str(comment_id), {})
        text = str(comment.get("text") or "")
        if len(text) > 16:
            text = text[:15] + "…"
        caption = nickname or "匿名"
        if text:
            caption = f"{caption}：{text}"
        if is_live:
            caption += "·动图"
        cap_label = EmojiText(cell, caption[:26], font=FONT_SMALL,
                              fg=TEXT_MUTED, bg="#FFFFFF", height=1,
                              width=16, wrap="none")
        cap_label.pack()

        select_var = tk.BooleanVar(value=False)
        check = tk.Checkbutton(cell, variable=select_var,
                               command=lambda k=key: self._checkbox_toggle(k),
                               relief="flat", bd=0, bg="#FFFFFF",
                               activebackground="#FFFFFF",
                               selectcolor="#FFFFFF", highlightthickness=0)
        check.place(x=_CELL_WIDTH - 24, y=2)

        self._cells[key] = {
            "frame": cell,
            "image_label": img_label,
            "photo": photo,
            "selected": False,
            "select_var": select_var,
            "comment_id": str(comment_id),
            "index": int(index),
            "is_live": bool(is_live),
        }
        img_label.bind("<Button-1>", lambda _e, k=key: self._zoom_cell(k))
        img_label.bind("<Double-Button-1>", lambda _e, k=key: self._toggle_select(k))
        cap_label.bind("<Button-1>", lambda _e, k=key: self._zoom_cell(k))
        cap_label.bind("<Double-Button-1>", lambda _e, k=key: self._toggle_select(k))

        self._cell_keys.append(key)
        self._reflow_grid()
        self._update_counts()

        # 评论卡片里的首图缩略图同步更新
        card_thumb = self._card_thumbs.get(str(comment_id))
        if card_thumb is not None and int(index) == 0:
            try:
                if card_thumb["label"].winfo_exists():
                    card_thumb["label"].configure(image=photo or "")
                    card_thumb["photo"] = photo
            except Exception:
                pass

    def finish_load(self, count: int, image_count: int, failed_thumbs: int):
        self._busy = False
        self.load_btn.configure(text="重新加载", state="normal")
        self.dl_btn.configure(state="normal" if self._selected else "disabled")
        self.export_btn.configure(state="normal")
        failed_note = f"，{failed_thumbs} 张缩略图失败" if failed_thumbs else ""
        self.status_label.configure(
            foreground=TEXT_MUTED,
            text=f"共 {count} 条评论、{image_count} 张图片{failed_note}；"
                 "单击图片放大，双击勾选，双击评论跳转图片")

    def show_load_error(self, message: str):
        """评论加载失败时给出明确提示，避免误以为列表空白。"""
        self._busy = False
        self.load_btn.configure(text="重新加载", state="normal")
        self.dl_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.status_label.configure(text=str(message), foreground="#B91C1C")

    def set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.load_btn.configure(state=state)
        self.dl_btn.configure(state="disabled" if busy or not self._selected
                              else "normal")

    def update_download_progress(self, current: int, total: int,
                                 success: int, failed: int, name: str):
        self.status_label.configure(
            text=f"正在下载 {current}/{total}：{name}（成功 {success}，失败 {failed}）")
        self.dl_btn.configure(text=f"下载中 {current}/{total}…", state="disabled")

    def finish_download(self, success: int, failed: int, save_dir: str):
        self._busy = False
        self.load_btn.configure(state="normal")
        self.dl_btn.configure(text=f"下载选中图片({len(self._selected)})",
                              state="normal" if self._selected else "disabled")
        if failed:
            self.status_label.configure(
                text=f"下载完成：成功 {success}，失败 {failed} → {save_dir}")
        else:
            self.status_label.configure(
                text=f"下载完成：成功 {success} 个文件 → {save_dir}")

    def show_zoom_result(self, ok: bool, path: str, error: str):
        if self._zoom_window is None or not self._zoom_window.winfo_exists():
            return
        for child in self._zoom_window.winfo_children():
            child.destroy()
        if ok and path and Path(path).exists():
            try:
                from PIL import Image, ImageTk

                image = Image.open(path)
                image.thumbnail((760, 640))
                photo = ImageTk.PhotoImage(image)
                label = tk.Label(self._zoom_window, image=photo, bg="#FFFFFF")
                label.image = photo  # keep reference
                label.pack(padx=8, pady=8)
            except Exception as exc:
                self._show_zoom_error(str(exc))
        else:
            self._show_zoom_error(error or "加载失败")

    def get_save_dir(self) -> str:
        return self.save_dir_var.get().strip()

    def get_aweme_id(self) -> str:
        return self._aweme_id

    # ── 评论卡片 ───────────────────────────────────────────────────

    def _build_card(self, cid: str) -> tk.Frame:
        """构建一张评论卡片（不打包，由虚拟列表按位置放置）。"""
        display = self._comments.get(cid, {})
        nickname = str(display.get("nickname") or "匿名")
        text = str(display.get("text") or "")
        image_count = int(display.get("image_count") or 0)
        live_count = int(display.get("live_image_count") or 0)

        card = tk.Frame(self._card_frame, bg="#FFFFFF",
                        highlightthickness=1, highlightbackground=BORDER)

        meta = tk.Frame(card, bg="#FFFFFF")
        meta.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(meta, text=nickname, font=FONT_BOLD, fg=BLUE,
                 bg="#FFFFFF").pack(side="left")
        meta_right = " · ".join(part for part in (
            str(display.get("time") or ""),
            str(display.get("ip_label") or ""),
            f"♥{display.get('digg_count') or 0}",
        ) if part)
        tk.Label(meta, text=meta_right, font=FONT_SMALL, fg=TEXT_MUTED,
                 bg="#FFFFFF").pack(side="right")

        if text:
            EmojiText(card, text, font=FONT, fg="#0F172A", bg="#FFFFFF",
                      width=28, usable_width=_CARD_WRAP
                      ).pack(anchor="w", padx=8, pady=(4, 2))

        if image_count:
            row = tk.Frame(card, bg="#FFFFFF")
            row.pack(fill="x", padx=8, pady=(0, 6))
            thumb_photo = self._thumb_photo_by_cid.get(cid)
            thumb_label = tk.Label(row, width=52, height=52, bg="#F1F5F9",
                                   image=thumb_photo or "",
                                   text="" if thumb_photo else "图片…")
            thumb_label.pack(side="left")
            note = f"共 {image_count} 张图"
            if live_count:
                note += f"（含 {live_count} 个动图）"
            tk.Label(row, text=note, font=FONT_SMALL, fg=TEXT_MUTED,
                     bg="#FFFFFF").pack(side="left", padx=(6, 0))
            if thumb_photo is not None:
                self._card_photos.append(thumb_photo)
            self._card_thumbs[cid] = {"label": thumb_label, "photo": thumb_photo}
            thumb_label.bind("<Button-1>",
                             lambda _e, cid_=cid: self._jump_to_comment_images(cid_))
            thumb_label.bind("<Double-Button-1>",
                             lambda _e, cid_=cid: self._jump_to_comment_images(cid_))

        # 双击卡片：有图片跳转首图，无图片看全文
        def _jump(_event=None, cid_=cid):
            self._jump_to_comment_images(cid_)

        for widget in (card, meta):
            widget.bind("<Double-Button-1>", _jump)
        for child in meta.winfo_children():
            child.bind("<Double-Button-1>", _jump)
        for child in card.winfo_children():
            if child is not meta:
                child.bind("<Double-Button-1>", _jump)

        return card

    # ── 搜索 / 筛选（按字段） ─────────────────────────────────────

    def _on_filter_typed(self, _event=None):
        self._filter_query = self.filter_entry.get().strip()
        self._filter_field = self.filter_field_var.get()
        self._apply_filter()

    def _apply_filter(self):
        query = self._filter_query
        field = self._filter_field
        visible = [
            cid for cid in self._comment_order
            if self._comment_matches(self._comments.get(cid, {}), query, field)
        ]
        self._visible_cids = visible
        self.comment_count.configure(
            text=f"评论：{len(visible)}/{len(self._comment_order)}")
        self._card_canvas.yview_moveto(0)
        self._schedule_card_refresh()

    @staticmethod
    def _comment_matches(comment: dict, query: str, field: str) -> bool:
        if not query:
            return True
        if field == "发送人":
            haystack = str(comment.get("nickname") or "")
        elif field == "时间":
            haystack = str(comment.get("time") or "")
        elif field == "IP属地":
            haystack = str(comment.get("ip_label") or "")
        elif field == "点赞":
            haystack = str(comment.get("digg_count") or "")
        elif field == "评论内容":
            haystack = str(comment.get("text") or "")
        else:  # 全部
            haystack = " ".join(
                str(comment.get(key) or "")
                for key in ("nickname", "time", "ip_label", "digg_count", "text"))
        return query.lower() in haystack.lower()

    # ── 卡片虚拟化：只渲染可视区域 ─────────────────────────────────

    def _card_offsets(self):
        offsets = []
        total = 0
        for cid in self._visible_cids:
            offsets.append(total)
            total += self._card_heights.get(cid, 110)
        return offsets, total

    def _update_card_view(self):
        self._card_refresh_job = None
        try:
            self._render_virtual()
        except Exception:
            # 虚拟渲染任何异常都回退到简单整列表渲染，保证列表不空白
            self._render_simple()

    def _render_virtual(self):
        for child in self._card_frame.winfo_children():
            child.destroy()
        self._rendered_cards.clear()
        self._card_photos.clear()
        if not self._visible_cids:
            self._card_frame.configure(height=1)
            self._card_canvas.configure(scrollregion=(0, 0, 1, 1))
            return

        offsets, total = self._card_offsets()
        width = max(100, self._card_canvas.winfo_width())
        y0 = max(0, int(self._card_canvas.canvasy(0)))
        viewport = max(50, self._card_canvas.winfo_height())
        at_bottom = y0 + viewport >= total - 2
        first = max(0, bisect_right(offsets, y0) - 1)
        last = min(len(self._visible_cids),
                   bisect_right(offsets, y0 + viewport) + 1)

        for index in range(first, last):
            cid = self._visible_cids[index]
            try:
                card = self._build_card(cid)
            except Exception:
                continue
            self._rendered_cards[cid] = card
            card.place(x=2, y=offsets[index], width=width - 4)
        self._card_frame.update_idletasks()
        for cid, card in self._rendered_cards.items():
            self._card_heights[cid] = max(40, card.winfo_reqheight())

        offsets2, total2 = self._card_offsets()
        self._card_frame.configure(height=total2)
        self._card_canvas.configure(scrollregion=(0, 0, width, total2))
        for index, cid in enumerate(self._visible_cids):
            card = self._rendered_cards.get(cid)
            if card is not None:
                card.place(x=2, y=offsets2[index], width=width - 4)
        if at_bottom and total2 > viewport:
            # 实际卡片高度大于估算时，总高会随测量增长；
            # 用户在底部时自动延伸到真实底部，保证最后几条可达
            self._card_canvas.yview_moveto((total2 - viewport) / total2)

    def _render_simple(self):
        """回退方案：整列表打包渲染（兼容旧版行为）。"""
        for child in self._card_frame.winfo_children():
            child.destroy()
        self._rendered_cards.clear()
        self._card_photos.clear()
        for cid in self._visible_cids:
            try:
                card = self._build_card(cid)
            except Exception:
                continue
            self._rendered_cards[cid] = card
            card.pack(fill="x", padx=2, pady=3)
        self._card_frame.update_idletasks()
        self._card_canvas.configure(
            scrollregion=self._card_canvas.bbox("all"))

    def refresh_view(self):
        """切到评论页签时调用：按当前实际尺寸重新渲染。"""
        self._schedule_card_refresh()

    def _scroll_cards(self, *args):
        self._card_canvas.yview(*args)
        self._schedule_card_refresh()

    def _schedule_card_refresh(self):
        self._cancel_card_refresh()
        self._card_refresh_job = self.after(40, self._update_card_view)

    def _cancel_card_refresh(self):
        if self._card_refresh_job is not None:
            try:
                self.after_cancel(self._card_refresh_job)
            except Exception:
                pass
            self._card_refresh_job = None

    def _jump_to_comment_images(self, cid: str):
        keys = [key for key in self._cell_keys if key.startswith(f"{cid}_")]
        if keys:
            # 仅高亮定位，不改变下载勾选状态
            self._highlight_image(keys[0])
        else:
            self._show_full_comment(cid)

    def _show_full_comment(self, cid: str):
        comment = self._comments.get(cid)
        if not comment:
            return
        window = tk.Toplevel(self)
        window.title("评论详情")
        window.geometry("560x320")
        window.configure(bg="#FFFFFF")
        meta = (f"{comment.get('nickname') or '匿名'} · "
                f"{comment.get('time') or '时间未知'}"
                + (f" · {comment.get('ip_label')}" if comment.get("ip_label") else "")
                + f" · 点赞 {comment.get('digg_count') or 0}")
        tk.Label(window, text=meta, bg="#FFFFFF", fg=TEXT_MUTED,
                 font=FONT_SMALL, anchor="w").pack(fill="x", padx=16, pady=(14, 6))
        text = EmojiText(window, comment.get("text") or "", font=FONT,
                         bg="#FFFFFF", fg="#0F172A", height=8, width=50,
                         wrap="word")
        text.pack(fill="both", expand=True, padx=10, pady=(0, 14))

    # ── selection / grid ───────────────────────────────────────────

    def _checkbox_toggle(self, key: str):
        cell = self._cells.get(key)
        if not cell:
            return
        cell["selected"] = bool(cell["select_var"].get())
        cell["frame"].configure(
            highlightbackground=BLUE if cell["selected"] else BORDER)
        self._sync_selected_set()
        self._update_counts()
        if not self._busy:
            self.dl_btn.configure(state="normal" if self._selected else "disabled")

    def _toggle_select(self, key: str):
        cell = self._cells.get(key)
        if not cell:
            return
        cell["selected"] = not cell["selected"]
        cell["select_var"].set(cell["selected"])
        cell["frame"].configure(
            highlightbackground=BLUE if cell["selected"] else BORDER)
        self._sync_selected_set()
        self._update_counts()
        if not self._busy:
            self.dl_btn.configure(state="normal" if self._selected else "disabled")

    def _sync_selected_set(self):
        self._selected = {
            key for key, cell in self._cells.items() if cell["selected"]
        }

    def _select_all(self):
        for key in self._cell_keys:
            cell = self._cells.get(key)
            if cell:
                cell["selected"] = True
                cell["select_var"].set(True)
                cell["frame"].configure(highlightbackground=BLUE)
        self._sync_selected_set()
        self._update_counts()
        if not self._busy:
            self.dl_btn.configure(state="normal" if self._selected else "disabled")

    def _clear_selection(self):
        for key in self._cell_keys:
            cell = self._cells.get(key)
            if cell:
                cell["selected"] = False
                cell["select_var"].set(False)
                cell["frame"].configure(highlightbackground=BORDER)
        self._sync_selected_set()
        self._update_counts()
        if not self._busy:
            self.dl_btn.configure(state="disabled")

    def _clear_grid(self):
        for child in self._grid_frame.winfo_children():
            child.destroy()
        self._cells.clear()
        self._cell_keys.clear()
        self._selected.clear()
        self._highlight_key = ""
        self._cell_photos.clear()
        self.grid_count.configure(text="评论图片：0")

    def _update_counts(self):
        self.grid_count.configure(text=f"评论图片：{len(self._cells)}"
                                  f"（已选 {len(self._selected)}）")
        if not self._busy:
            self.dl_btn.configure(
                text=f"下载选中图片({len(self._selected)})",
                state="normal" if self._selected else "disabled")

    def _reflow_grid(self):
        for index, key in enumerate(self._cell_keys):
            cell = self._cells.get(key)
            if not cell:
                continue
            row = index // _GRID_COLUMNS
            col = index % _GRID_COLUMNS
            cell["frame"].grid(row=row, column=col, padx=3, pady=3, sticky="nw")

    def _on_canvas_resize(self, event):
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _on_card_canvas_resize(self, event):
        self._card_canvas.itemconfigure(self._card_window, width=event.width)
        self._schedule_card_refresh()

    def _on_mousewheel(self, event):
        widget = self._canvas.winfo_containing(event.x_root, event.y_root)
        while widget is not None and widget not in (self._canvas,
                                                    self._card_canvas):
            widget = widget.master
        if widget == self._canvas:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")
        elif widget == self._card_canvas:
            self._card_canvas.yview_scroll(int(-event.delta / 120), "units")
            self._schedule_card_refresh()

    def _highlight_image(self, key: str):
        """框选提示并滚动到可见位置。"""
        if self._highlight_key:
            prev = self._cells.get(self._highlight_key)
            if prev:
                prev["frame"].configure(
                    highlightthickness=2,
                    highlightbackground=BLUE if prev["selected"] else BORDER)
        cell = self._cells.get(key)
        if not cell:
            return
        self._highlight_key = key
        cell["frame"].configure(highlightthickness=3, highlightbackground=BLUE)
        self._grid_frame.update_idletasks()
        canvas_height = self._canvas.winfo_height()
        total_height = self._grid_frame.winfo_reqheight()
        y = cell["frame"].winfo_y()
        fraction = max(0.0, min(1.0, (y - 8) / max(1, total_height - canvas_height)))
        self._canvas.yview_moveto(fraction)

    # ── zoom ───────────────────────────────────────────────────────

    def _zoom_cell(self, key: str):
        cell = self._cells.get(key)
        if not cell:
            return
        self._open_zoom_window()
        self.status_label.configure(text="正在加载原图预览…")
        self.on_zoom(key, cell.get("comment_id", ""), cell.get("index", 0))

    def _open_zoom_window(self):
        if self._zoom_window is not None and self._zoom_window.winfo_exists():
            self._zoom_window.destroy()
        window = tk.Toplevel(self)
        window.title("图片预览")
        window.geometry("800x700")
        window.configure(bg="#FFFFFF")
        tk.Label(window, text="加载中…", bg="#FFFFFF",
                 font=FONT).pack(expand=True)
        self._zoom_window = window

    def _show_zoom_error(self, error: str):
        if self._zoom_window is None or not self._zoom_window.winfo_exists():
            return
        for child in self._zoom_window.winfo_children():
            child.destroy()
        tk.Label(self._zoom_window, text=f"图片加载失败：{error}",
                 bg="#FFFFFF", fg="#B91C1C", font=FONT,
                 wraplength=700).pack(expand=True)
        self.status_label.configure(text="原图预览失败，请稍后重试")

    # ── download / export ──────────────────────────────────────────

    def _on_download(self):
        if self._busy or not self._selected:
            return
        images = []
        for key in self._cell_keys:
            if key in self._selected:
                cell = self._cells.get(key)
                if cell:
                    images.append({
                        "comment_id": cell["comment_id"],
                        "index": cell["index"],
                        "is_live": cell["is_live"],
                    })
        if not images:
            return
        self.on_download(images, self.get_save_dir())

    def _on_export(self):
        if not self._comments:
            return
        from core.comment_export import export_comments_to_excel

        default_name = f"{self._aweme_id}_评论.xlsx" if self._aweme_id else "评论.xlsx"
        path = filedialog.asksaveasfilename(
            parent=self,
            title="导出评论到 Excel",
            defaultextension=".xlsx",
            initialfile=default_name,
            filetypes=[("Excel 工作簿", "*.xlsx")],
        )
        if not path:
            return
        images = []
        for key in self._cell_keys:
            cell = self._cells.get(key)
            if not cell:
                continue
            comment = self._comments.get(cell["comment_id"], {})
            images.append({
                "comment_id": cell["comment_id"],
                "index": cell["index"],
                "is_live": cell["is_live"],
                "nickname": comment.get("nickname", ""),
                "text": comment.get("text", ""),
            })
        ok = export_comments_to_excel(
            list(self._comments.values()),
            images,
            path,
            aweme_id=self._aweme_id,
            aweme_title=self._title,
        )
        if ok:
            messagebox.showinfo("导出完成", f"已导出到：\n{path}", parent=self)
        else:
            messagebox.showerror("导出失败", "Excel 导出失败，请检查文件是否被占用。",
                                 parent=self)

    @staticmethod
    def _load_thumb(thumb_path):
        if not thumb_path or not Path(thumb_path).exists():
            return None
        try:
            from PIL import Image, ImageTk

            image = Image.open(thumb_path)
            image.thumbnail((_CELL_WIDTH - 16, _CELL_HEIGHT - 62))
            return ImageTk.PhotoImage(image)
        except Exception:
            return None
