"""评论导出 Excel 测试。"""

from openpyxl import load_workbook

from core.comment_export import export_comments_to_excel


def test_export_comments_to_excel(tmp_path):
    comments = [
        {
            "nickname": "小明",
            "time": "2026-08-01 10:00",
            "ip_label": "广东",
            "digg_count": 5,
            "text": "这个视频很好看 😀",
            "image_count": 1,
            "live_image_count": 0,
        },
        {
            "nickname": "小红",
            "time": "2026-08-01 11:00",
            "ip_label": "",
            "digg_count": 2,
            "text": "",
            "image_count": 1,
            "live_image_count": 1,
        },
    ]
    images = [
        {"comment_id": "c1", "index": 0, "is_live": False,
         "nickname": "小明", "text": "这个视频很好看 😀"},
        {"comment_id": "c2", "index": 0, "is_live": True,
         "nickname": "小红", "text": ""},
    ]
    output = tmp_path / "评论.xlsx"

    ok = export_comments_to_excel(
        comments, images, output, aweme_id="A1", aweme_title="测试作品")

    assert ok is True
    assert output.exists()
    wb = load_workbook(output)
    assert wb.sheetnames == ["评论列表", "图片明细"]

    ws = wb["评论列表"]
    assert ws.cell(row=1, column=1).value == "作品ID：A1"
    assert ws.cell(row=4, column=2).value == "发送人"
    assert ws.cell(row=5, column=2).value == "小明"
    assert ws.cell(row=5, column=6).value == "这个视频很好看 😀"
    assert ws.cell(row=6, column=8).value == "是"

    ws2 = wb["图片明细"]
    assert ws2.cell(row=1, column=1).value == "评论ID"
    assert ws2.cell(row=2, column=2).value == 1
    assert ws2.cell(row=3, column=4).value == "是"
