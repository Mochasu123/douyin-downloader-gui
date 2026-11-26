"""Live Photo 合并工具测试（Android Motion Photo + 荣耀/华为通用封装）。"""

from io import BytesIO
from pathlib import Path

import pytest

from core.live_photo import (
    build_footer,
    merge_live_photo_bytes,
    merge_live_photo_files,
    normalize_live_photo_format,
    parse_footer,
    parse_motion_photo_offset,
    verify_live_photo,
)


def _jpeg_bytes():
    return b"\xff\xd8\xff\xe0" + b"JPG-DATA" * 16


def _real_jpeg_bytes():
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (24, 24), (220, 60, 40)).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _video_bytes():
    return b"\x00\x00\x00\x18ftypmp42" + b"MP4-DATA" * 32


def test_build_and_parse_footer_roundtrip():
    video_size = 1024
    footer = build_footer(video_size)
    assert len(footer) == 20
    assert footer.startswith(b"LIVE_")
    parsed = parse_footer(b"prefix" + footer)
    assert parsed == ("000000000001024", 1024)


def test_normalize_live_photo_format():
    assert normalize_live_photo_format(None) == "universal"
    assert normalize_live_photo_format("ANDROID") == "android"
    assert normalize_live_photo_format("huawei") == "huawei"
    assert normalize_live_photo_format("unknown") == "universal"


def test_merge_live_photo_bytes_structure():
    image = _jpeg_bytes()
    video = _video_bytes()

    huawei_merged = merge_live_photo_bytes(image, video, format_mode="huawei")
    assert huawei_merged == image + video + build_footer(len(video))
    assert parse_footer(huawei_merged) == (f"{len(video):015d}", len(video))

    android_merged = merge_live_photo_bytes(image, video, format_mode="android")
    assert parse_footer(android_merged) is None
    assert android_merged.endswith(video)
    assert parse_motion_photo_offset(android_merged) == len(video)

    universal_merged = merge_live_photo_bytes(image, video, format_mode="universal")
    assert parse_footer(universal_merged) == (f"{len(video):015d}", len(video))
    assert parse_motion_photo_offset(universal_merged) == len(video) + 20


def test_universal_and_android_real_jpeg_xmp_and_exif_offsets(tmp_path):
    from PIL import Image

    jpeg = _real_jpeg_bytes()
    video = _video_bytes()

    # 1. Universal mode: XMP MotionPhoto + MicroVideo + OPPO + EXIF UserComment + LIVE_ footer
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

    offset = parse_motion_photo_offset(uni_bytes)
    assert offset == len(video) + 20
    assert uni_bytes[-offset : -offset + len(video)] == video
    assert parse_footer(uni_bytes) == (f"{len(video):015d}", len(video))
    assert verify_live_photo(uni_path) == (True, f"{len(video):015d}", len(video))

    # 2. Pure Android mode: standard Motion Photo XMP + EXIF UserComment, no LIVE_ footer
    and_path = tmp_path / "android_live.jpg"
    and_bytes = merge_live_photo_bytes(jpeg, video, format_mode="android")
    and_path.write_bytes(and_bytes)

    with Image.open(BytesIO(and_bytes)) as img:
        assert img.size == (24, 24)
        assert img.getexif().get_ifd(0x8769).get(0x9286) == b"ASCII\x00\x00\x00oplus_8388608"

    assert parse_footer(and_bytes) is None
    assert parse_motion_photo_offset(and_bytes) == len(video)
    assert and_bytes[-len(video) :] == video
    assert verify_live_photo(and_path) == (True, "MOTION_PHOTO", len(video))


def test_parse_footer_rejects_unknown_format():
    assert parse_footer(b"not-a-live-photo") is None
    assert parse_footer(b"") is None
    assert parse_footer(b"LIVE_abc" * 5) is None


def test_merge_files_jpeg_huawei_stays_raw(tmp_path):
    image_path = tmp_path / "still.jpg"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / "live.jpg"
    image_path.write_bytes(_jpeg_bytes())
    video_path.write_bytes(_video_bytes())

    result = merge_live_photo_files(image_path, video_path, output_path, format_mode="huawei")
    assert result == output_path
    assert output_path.exists()
    data = output_path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")
    assert parse_footer(data) == (f"{len(_video_bytes()):015d}", len(_video_bytes()))
    assert verify_live_photo(output_path) == (
        True,
        f"{len(_video_bytes()):015d}",
        len(_video_bytes()),
    )


@pytest.mark.parametrize("format_mode", ["universal", "android"])
def test_merge_files_converts_webp_still_to_jpeg(tmp_path, format_mode):
    from PIL import Image

    webp_buffer = BytesIO()
    Image.new("RGB", (8, 8), (10, 120, 200)).save(webp_buffer, format="WEBP")
    image_path = tmp_path / "still.webp"
    video_path = tmp_path / "video.mp4"
    output_path = tmp_path / f"live_{format_mode}.jpg"
    image_path.write_bytes(webp_buffer.getvalue())
    video_path.write_bytes(_video_bytes())

    result = merge_live_photo_files(image_path, video_path, output_path, format_mode=format_mode)
    assert result == output_path
    data = output_path.read_bytes()
    assert data.startswith(b"\xff\xd8\xff")  # 已转为 JPEG
    ok, _tag, size = verify_live_photo(output_path)
    assert ok is True
    expected_size = len(_video_bytes()) + (20 if format_mode == "universal" else 0)
    if format_mode == "universal":
        assert parse_footer(data)[1] == len(_video_bytes())
        assert parse_motion_photo_offset(data) == expected_size
    else:
        assert size == len(_video_bytes())


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
