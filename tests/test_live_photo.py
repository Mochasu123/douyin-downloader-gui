"""Live Photo 合并工具测试。"""

from pathlib import Path

import pytest

from core.live_photo import (
    build_footer,
    merge_live_photo_bytes,
    merge_live_photo_files,
    parse_footer,
    verify_live_photo,
)


def _jpeg_bytes():
    return b"\xff\xd8\xff\xe0" + b"JPG-DATA" * 16


def _video_bytes():
    return b"\x00\x00\x00\x18ftypmp42" + b"MP4-DATA" * 32


def test_build_and_parse_footer_roundtrip():
    video_size = 1024
    footer = build_footer(video_size)
    assert len(footer) == 20
    assert footer.startswith(b"LIVE_")
    parsed = parse_footer(b"prefix" + footer)
    assert parsed == ("000000000001024", 1024)


def test_merge_live_photo_bytes_structure():
    image = _jpeg_bytes()
    video = _video_bytes()
    merged = merge_live_photo_bytes(image, video)
    assert merged == image + video + build_footer(len(video))
    assert parse_footer(merged) == (f"{len(video):015d}", len(video))


def test_parse_footer_rejects_unknown_format():
    assert parse_footer(b"not-a-live-photo") is None
    assert parse_footer(b"") is None
    assert parse_footer(b"LIVE_abc" * 5) is None


def test_merge_files_jpeg_stays_raw(tmp_path):
    image_path = tmp_path / "still.jpg"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / "live.jpg"
    image_path.write_bytes(_jpeg_bytes())
    video_path.write_bytes(_video_bytes())

    result = merge_live_photo_files(image_path, video_path, output_path)
    assert result == output_path
    assert output_path.exists()
    data = output_path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")
    assert parse_footer(data) == (f"{len(_video_bytes()):015d}", len(_video_bytes()))
    assert verify_live_photo(output_path) == (
        True, f"{len(_video_bytes()):015d}", len(_video_bytes()))


def test_merge_files_converts_webp_still_to_jpeg(tmp_path):
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed")

    from io import BytesIO

    webp_buffer = BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(webp_buffer, format="WEBP")
    image_path = tmp_path / "still.webp"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / "live.jpg"
    image_path.write_bytes(webp_buffer.getvalue())
    video_path.write_bytes(_video_bytes())

    result = merge_live_photo_files(image_path, video_path, output_path)
    assert result == output_path
    data = output_path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")  # 已转为 JPEG
    assert parse_footer(data)[1] == len(_video_bytes())


def test_merge_files_empty_input_returns_none(tmp_path):
    image_path = tmp_path / "still.jpg"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / "live.jpg"
    image_path.write_bytes(b"")
    video_path.write_bytes(_video_bytes())
    assert merge_live_photo_files(image_path, video_path, output_path) is None
    assert not output_path.exists()


def test_verify_live_photo_rejects_corrupt(tmp_path):
    path = tmp_path / "bad.jpg"
    path.write_bytes(_jpeg_bytes() + _video_bytes() + b"LIVE_999999999999999")
    ok, footer, size = verify_live_photo(path)
    assert ok is False
    assert footer == "999999999999999"
    assert size == 999999999999999


def test_merge_files_missing_source_returns_none(tmp_path):
    assert merge_live_photo_files(
        tmp_path / "no.jpg", tmp_path / "no.mp4", tmp_path / "out.jpg") is None
