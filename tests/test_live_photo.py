"""Live Photo 合并工具测试（Android Motion Photo + 华为/荣耀 60B 尾标）。"""

from io import BytesIO
import struct
from pathlib import Path

import pytest

from core.live_photo import (
    build_footer,
    build_huawei_trailer,
    extract_huawei_mp4_span,
    merge_live_photo_bytes,
    merge_live_photo_files,
    normalize_live_photo_format,
    parse_footer,
    parse_motion_photo_offset,
    read_video_size_from_footer,
    verify_live_photo,
)


def _jpeg_bytes():
    return b"\xff\xd8\xff\xe0" + b"JPG-DATA" * 16


def _real_jpeg_bytes():
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (24, 24), (220, 60, 40)).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _video_bytes(duration_ms: int = 1560):
    def box(box_type: bytes, payload: bytes) -> bytes:
        return struct.pack(">I4s", 8 + len(payload), box_type) + payload

    ftyp = box(b"ftyp", b"mp42\x00\x00\x00\x00mp42isom")
    mvhd_payload = struct.pack(">BBBBIIII", 0, 0, 0, 0, 0, 0, 1000, duration_ms) + b"\x00" * 80
    mvhd = box(b"mvhd", mvhd_payload)
    moov = box(b"moov", mvhd)
    mdat = box(b"mdat", b"MP4-DATA" * 32)
    return ftyp + mdat + moov


def test_build_and_parse_footer_and_huawei_trailer_roundtrip():
    footer = build_footer(1024)
    assert len(footer) == 20
    assert footer == b"LIVE_1024           "
    assert parse_footer(b"prefix" + footer) == ("1024", 1024)
    # Backward compatibility for legacy zero-padded 20-byte footer
    assert parse_footer(b"prefix" + b"LIVE_000000000001024") == ("000000000001024", 1024)

    trailer = build_huawei_trailer(2565615, duration_ms=1560, cover_frame=0)
    assert len(trailer) == 60
    assert trailer[0:20] == b"v6_f0               "
    assert trailer[20:40] == b"0:1560              "
    assert trailer[40:60] == b"LIVE_2565635        "


def test_normalize_live_photo_format():
    assert normalize_live_photo_format(None) == "universal"
    assert normalize_live_photo_format("ANDROID") == "android"
    assert normalize_live_photo_format("huawei") == "huawei"
    assert normalize_live_photo_format("unknown") == "universal"


def test_merge_live_photo_bytes_structure():
    image = _jpeg_bytes()
    video = _video_bytes(duration_ms=2970)
    vlen = len(video)

    huawei_merged = merge_live_photo_bytes(image, video, format_mode="huawei")
    assert len(huawei_merged) == len(image) + vlen + 60
    assert huawei_merged[-60:-40] == b"v6_f0               "
    assert huawei_merged[-40:-20] == b"0:2970              "
    assert parse_footer(huawei_merged) == (str(vlen + 20), vlen + 20)
    span = extract_huawei_mp4_span(huawei_merged)
    assert span is not None and huawei_merged[span[0] : span[1]] == video

    android_merged = merge_live_photo_bytes(image, video, format_mode="android")
    assert parse_footer(android_merged) is None
    assert android_merged.endswith(video)
    assert parse_motion_photo_offset(android_merged) == vlen

    universal_merged = merge_live_photo_bytes(image, video, format_mode="universal")
    assert universal_merged[-60:-40] == b"v6_f0               "
    assert universal_merged[-40:-20] == b"0:2970              "
    assert parse_footer(universal_merged) == (str(vlen + 20), vlen + 20)
    assert parse_motion_photo_offset(universal_merged) == vlen + 60


def test_universal_and_android_real_jpeg_xmp_and_exif_offsets(tmp_path):
    from PIL import Image

    jpeg = _real_jpeg_bytes()
    video = _video_bytes(duration_ms=1560)
    vlen = len(video)

    # 1. Universal mode: XMP MotionPhoto + MicroVideo + OPPO + EXIF UserComment + 60B Huawei trailer
    uni_path = tmp_path / "uni_live.jpg"
    uni_bytes = merge_live_photo_bytes(jpeg, video, format_mode="universal")
    uni_path.write_bytes(uni_bytes)

    with Image.open(BytesIO(uni_bytes)) as img:
        assert img.size == (24, 24)
        user_comment = img.getexif().get_ifd(0x8769).get(0x9286)
        assert user_comment == b"ASCII\x00\x00\x00oplus_8388608"
        xmp_raw = img.info.get("xmp") or b""
        assert b'GCamera:MotionPhoto="1"' in xmp_raw
        assert b"Container:Directory" in xmp_raw
        assert b'OpCamera:MotionPhotoOwner="oplus"' in xmp_raw
        assert b'OpCamera:OLivePhotoVersion="2"' in xmp_raw

    # Android MotionPhoto offset points to exact MP4 start; Huawei EOF-40-LIVE_val ALSO points to exact MP4 start!
    xmp_offset = parse_motion_photo_offset(uni_bytes)
    assert xmp_offset == vlen + 60
    assert uni_bytes[-xmp_offset : -xmp_offset + vlen] == video
    hw_span = extract_huawei_mp4_span(uni_bytes)
    assert hw_span == (len(uni_bytes) - 40 - (vlen + 20), len(uni_bytes) - 60)
    assert hw_span[0] == len(uni_bytes) - xmp_offset
    assert uni_bytes[hw_span[0] : hw_span[1]] == video
    assert parse_footer(uni_bytes) == (str(vlen + 20), vlen + 20)
    assert verify_live_photo(uni_path) == (True, str(vlen + 20), vlen)
    assert read_video_size_from_footer(uni_path) == vlen

    # 2. Pure Android mode: standard Motion Photo XMP + EXIF UserComment, no LIVE_ footer
    and_path = tmp_path / "android_live.jpg"
    and_bytes = merge_live_photo_bytes(jpeg, video, format_mode="android")
    and_path.write_bytes(and_bytes)

    with Image.open(BytesIO(and_bytes)) as img:
        assert img.size == (24, 24)
        assert img.getexif().get_ifd(0x8769).get(0x9286) == b"ASCII\x00\x00\x00oplus_8388608"

    assert parse_footer(and_bytes) is None
    assert parse_motion_photo_offset(and_bytes) == vlen
    assert and_bytes[-vlen:] == video
    assert verify_live_photo(and_path) == (True, "MOTION_PHOTO", vlen)


def test_parse_footer_rejects_unknown_format():
    assert parse_footer(b"not-a-live-photo") is None
    assert parse_footer(b"") is None
    assert parse_footer(b"LIVE_abc" * 5) is None


def test_merge_files_jpeg_huawei_writes_60b_trailer(tmp_path):
    image_path = tmp_path / "still.jpg"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / "live.jpg"
    video = _video_bytes(duration_ms=2100)
    image_path.write_bytes(_jpeg_bytes())
    video_path.write_bytes(video)

    result = merge_live_photo_files(image_path, video_path, output_path, format_mode="huawei")
    assert result == output_path
    assert output_path.exists()
    data = output_path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")
    assert data[-60:-40] == b"v6_f0               "
    assert data[-40:-20] == b"0:2100              "
    assert parse_footer(data) == (str(len(video) + 20), len(video) + 20)
    assert verify_live_photo(output_path) == (True, str(len(video) + 20), len(video))


@pytest.mark.parametrize("format_mode", ["universal", "android"])
def test_merge_files_converts_webp_still_to_jpeg(tmp_path, format_mode):
    from PIL import Image

    webp_buffer = BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(webp_buffer, format="WEBP")
    image_path = tmp_path / "still.webp"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / f"live_{format_mode}.jpg"
    video = _video_bytes()
    image_path.write_bytes(webp_buffer.getvalue())
    video_path.write_bytes(video)

    result = merge_live_photo_files(image_path, video_path, output_path, format_mode=format_mode)
    assert result == output_path
    data = output_path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")  # 已转为 JPEG
    ok, _tag, size = verify_live_photo(output_path)
    assert ok is True
    assert size == len(video)
    if format_mode == "universal":
        assert parse_footer(data) == (str(len(video) + 20), len(video) + 20)
        assert parse_motion_photo_offset(data) == len(video) + 60


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
    assert (
        merge_live_photo_files(tmp_path / "no.jpg", tmp_path / "no.mp4", tmp_path / "out.jpg")
        is None
    )
