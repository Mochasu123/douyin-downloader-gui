"""Emoji 感知文本组件。

Windows 下单一字体无法同时覆盖中文与彩色 Emoji（微软雅黑无 Emoji 字形，
Segoe UI Emoji 无中文字形），Tk 的字体回退在绘制时不可靠。该组件把文本
按 Emoji 区间分段：中文用主字体，Emoji 用 Segoe UI Emoji 字体，混排显示。
"""

from __future__ import annotations

import math
import re
import tkinter as tk
import tkinter.font as tkfont

# 常见 Emoji 区间（覆盖主要表情、符号、旗帜、ZWJ/VS16/Keycap 组合符）
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U0001F1E6-\U0001F1FF"
    "\u2600-\u27BF"
    "\u2B00-\u2BFF"
    "\u2300-\u23FF"
    "\u25A0-\u25FF"
    "\u2700-\u27BF"
    "\uFE0F\u200D\u20E3"
    "\u3030\u303D\u3297\u3299"
    "]"
)


def emoji_ranges(text: str):
    """返回 [(start, end), ...]，end 为开区间，连续 Emoji 合并为一段。"""
    ranges = []
    start = None
    for index, char in enumerate(text):
        if _EMOJI_RE.match(char):
            if start is None:
                start = index
        elif start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(text)))
    return ranges


def _estimate_lines(text: str, font, usable_width: int = 330) -> int:
    if not text:
        return 1
    try:
        tkfont.Font(family=font[0], size=font[1])
        width = tkfont.Font(family=font[0], size=font[1]).measure(text)
    except Exception:
        width = len(text) * 12
    return max(1, min(6, math.ceil(width / max(1, usable_width))))


def _text_index(text: str, position: int) -> str:
    """把绝对字符位置转成 Tk 的 line.column 索引（文本可能含换行）。"""
    before = text[:position]
    line = before.count("\n") + 1
    column = position - (before.rfind("\n") + 1)
    return f"{line}.{column}"


class EmojiText(tk.Text):
    """只读文本：中文 + Emoji 混排显示。"""

    def __init__(self, parent, text="", *, font=None, emoji_font=None,
                 height=None, width=None, wrap="word", max_lines=6,
                 fg="#0F172A", bg="#FFFFFF", usable_width=330, **kw):
        self._font = font or ("Microsoft YaHei UI", 10)
        self._emoji_font = emoji_font or ("Segoe UI Emoji", 10)
        if height is None:
            height = _estimate_lines(text, self._font, usable_width)
        super().__init__(
            parent,
            height=height,
            width=width,
            wrap=wrap,
            font=self._font,
            fg=fg,
            bg=bg,
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            takefocus=0,
            cursor="arrow",
            **kw,
        )
        self.tag_configure("emoji", font=self._emoji_font)
        self.insert("1.0", text)
        for start, end in emoji_ranges(text):
            self.tag_add("emoji", _text_index(text, start), _text_index(text, end))
        self.configure(state="disabled")
