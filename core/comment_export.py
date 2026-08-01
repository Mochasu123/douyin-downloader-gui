"""评论列表导出 Excel（含图片明细），便于统计。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from utils.logger import setup_logger

logger = setup_logger("CommentExport")


def export_comments_to_excel(
    comments: List[Dict[str, Any]],
    images: List[Dict[str, Any]],
    output_path,
    *,
    aweme_id: str = "",
    aweme_title: str = "",
) -> bool:
    """导出评论列表与图片明细到 .xlsx，成功返回 True。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "评论列表"
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2563EB")

    if aweme_id:
        ws.append([f"作品ID：{aweme_id}"])
        ws.append([f"作品标题：{aweme_title}"])
        ws.append([])
        header_row = 4
    else:
        header_row = 1

    headers = ["序号", "发送人", "时间", "IP属地", "点赞", "评论内容", "图片数", "含动图"]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=text)
        cell.font = header_font
        cell.fill = header_fill

    for index, comment in enumerate(comments, start=1):
        image_count = int(comment.get("image_count") or 0)
        live_count = int(comment.get("live_image_count") or 0)
        ws.append([
            index,
            comment.get("nickname") or "",
            comment.get("time") or "",
            comment.get("ip_label") or "",
            comment.get("digg_count") or 0,
            comment.get("text") or "",
            image_count,
            "是" if live_count else "否",
        ])

    widths = {"A": 6, "B": 18, "C": 18, "D": 10, "E": 8, "F": 60, "G": 8, "H": 8}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    ws2 = wb.create_sheet("图片明细")
    headers2 = ["评论ID", "图片序号", "发送人", "是否动图", "图片说明"]
    for col, text in enumerate(headers2, start=1):
        cell = ws2.cell(row=1, column=col, value=text)
        cell.font = header_font
        cell.fill = header_fill
    for index, image in enumerate(images, start=1):
        ws2.append([
            image.get("comment_id") or "",
            int(image.get("index") or 0) + 1,
            image.get("nickname") or "",
            "是" if image.get("is_live") else "否",
            image.get("text") or "",
        ])
    for col in range(1, len(headers2) + 1):
        ws2.column_dimensions[get_column_letter(col)].width = 20

    try:
        wb.save(str(output))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Export comments to excel failed: %s", exc)
        return False
    return True
