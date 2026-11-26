"""Live Photo 合并工具：单文件动态照片封装（Android Motion Photo + 华为/荣耀 60B 尾标）。

实测 HUAWEI Mate 80 Pro (OpenHarmony 6.1) 真机动态照片二进制结构：
``[JPEG] + [MP4 (V 字节)] + [v6_f0 (20B 空格填充)] + [0:<dur_ms> (20B 空格填充)] + [LIVE_<V+20> (20B 空格填充)]``
其中华为相册按 ``EOF - 40 - LIVE_val`` 定位 MP4 起点、按 ``EOF - 60`` 定位 MP4 终点；
``universal`` 模式在 JPEG 头同时注入 Google Motion Photo v1.0 / MicroVideo XMP（偏移
设为 ``V + 60``）与 OPPO EXIF ``UserComment``，使单一文件同时对齐安卓通用相册与华为/荣耀。
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path
from typing import List, Optional, Tuple

from utils.logger import setup_logger

logger = setup_logger("LivePhoto")

LIVE_RAW_DIR_NAME = "实况素材"
LIVE_MERGED_DIR_NAME = "合成动图"

LIVE_PHOTO_FORMATS = ("universal", "android", "huawei")
DEFAULT_LIVE_PHOTO_FORMAT = "universal"

_FOOTER_PREFIX = b"LIVE_"
_FOOTER_LENGTH = 20
_HUAWEI_TRAILER_LENGTH = 60
_V_TAG_RE = re.compile(rb"^v\d+_f\d+\s*$")

_XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
_EXIF_HEADER = b"Exif\x00\x00"
_OPLUS_USER_COMMENT = b"ASCII\x00\x00\x00oplus_8388608"

_STANDALONE_MARKERS = frozenset({0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9})
_XMP_ITEM_LENGTH_RE = re.compile(
    rb'Item:Semantic="MotionPhoto"[^>]*?Item:Length="(\d+)"'
    rb'|Item:Length="(\d+)"[^>]*?Item:Semantic="MotionPhoto"',
    re.DOTALL,
)
_XMP_MICRO_OFFSET_RE = re.compile(rb'GCamera:MicroVideoOffset="(\d+)"')


def normalize_live_photo_format(mode: Optional[str]) -> str:
    """规范化实况动图封装格式，未知值回退为 ``universal``。"""
    cleaned = str(mode or "").strip().lower()
    if cleaned in LIVE_PHOTO_FORMATS:
        return cleaned
    return DEFAULT_LIVE_PHOTO_FORMAT


def _read_mp4_duration_ms(video_bytes: bytes) -> int:
    """从 MP4 ``moov -> mvhd`` 中解析视频总时长（毫秒）；异常或截断时返回 0。"""
    n = len(video_bytes)
    pos = 0
    moov_span: Optional[Tuple[int, int]] = None
    while pos + 8 <= n:
        box_size, box_type = struct.unpack(">I4s", video_bytes[pos : pos + 8])
        header_len = 8
        if box_size == 1:
            if pos + 16 > n:
                return 0
            box_size = struct.unpack(">Q", video_bytes[pos + 8 : pos + 16])[0]
            header_len = 16
        elif box_size == 0:
            box_size = n - pos
        if box_size < header_len or pos + box_size > n:
            return 0
        if box_type == b"moov":
            moov_span = (pos + header_len, pos + box_size)
            break
        pos += box_size

    if moov_span is None:
        return 0

    mpos, mend = moov_span
    while mpos + 8 <= mend:
        box_size, box_type = struct.unpack(">I4s", video_bytes[mpos : mpos + 8])
        header_len = 8
        if box_size == 1:
            if mpos + 16 > mend:
                return 0
            box_size = struct.unpack(">Q", video_bytes[mpos + 8 : mpos + 16])[0]
            header_len = 16
        elif box_size == 0:
            box_size = mend - mpos
        if box_size < header_len or mpos + box_size > mend:
            return 0
        if box_type == b"mvhd":
            payload_start = mpos + header_len
            if payload_start + 20 > mpos + box_size:
                return 0
            version = video_bytes[payload_start]
            if version == 0:
                timescale, duration = struct.unpack(
                    ">II", video_bytes[payload_start + 12 : payload_start + 20]
                )
            elif version == 1:
                if payload_start + 32 > mpos + box_size:
                    return 0
                timescale, duration = struct.unpack(
                    ">IQ", video_bytes[payload_start + 20 : payload_start + 32]
                )
            else:
                return 0
            if timescale <= 0 or duration <= 0:
                return 0
            return int(round(duration * 1000.0 / timescale))
        mpos += box_size
    return 0


def build_footer(video_size: int) -> bytes:
    """构造尾部 20 字节：``LIVE_<长度>`` 左对齐并以 ASCII 空格右填充至 20 字节。"""
    if video_size < 0:
        raise ValueError("video_size must be non-negative")
    text = f"LIVE_{int(video_size)}"
    if len(text) > _FOOTER_LENGTH:
        raise ValueError("video_size too large for 20-byte LIVE_ footer")
    return text.ljust(_FOOTER_LENGTH).encode("ascii")


def build_huawei_trailer(
    video_size: int,
    *,
    duration_ms: int = 0,
    cover_frame: int = 0,
) -> bytes:
    """构造 60 字节华为/荣耀动态照片尾标（3 × 20 字节左对齐空格填充）。"""
    if video_size < 0:
        raise ValueError("video_size must be non-negative")
    block1 = f"v6_f{max(0, int(cover_frame))}".ljust(_FOOTER_LENGTH)[:_FOOTER_LENGTH].encode("ascii")
    block2 = f"0:{max(0, int(duration_ms))}".ljust(_FOOTER_LENGTH)[:_FOOTER_LENGTH].encode("ascii")
    block3 = build_footer(int(video_size) + _FOOTER_LENGTH)
    return block1 + block2 + block3


def parse_footer(data: bytes) -> Optional[Tuple[str, int]]:
    """解析文件末尾 20 字节 ``LIVE_`` 字段（兼容空格填充与旧版零填充）；非 ``LIVE_`` 时返回 None。"""
    if not data or len(data) < _FOOTER_LENGTH:
        return None
    footer = data[-_FOOTER_LENGTH:]
    if not footer.startswith(_FOOTER_PREFIX):
        return None
    size_text = footer[len(_FOOTER_PREFIX) :].rstrip(b" ").decode("ascii", errors="replace")
    if not size_text or not size_text.isdigit():
        return None
    return size_text, int(size_text)


def extract_huawei_mp4_span(data: bytes) -> Optional[Tuple[int, int]]:
    """根据华为/荣耀尾标推算内嵌 MP4 的 ``(start, end)`` 字节区间（支持 60B/40B/20B）。"""
    parsed = parse_footer(data)
    if parsed is None:
        return None
    _size_text, live_val = parsed
    n = len(data)
    if n >= 60 and _V_TAG_RE.match(data[-60:-40]) and live_val > 20:
        start = n - 40 - live_val
        end = n - 60
        return (start, end) if 0 < start < end else None
    if n >= 40 and b":" in data[-40:-20]:
        start = n - 40 - live_val
        end = n - 40
        return (start, end) if 0 < start < end else None
    start = n - 20 - live_val
    end = n - 20
    return (start, end) if 0 < start < end else None


def build_motion_photo_xmp(video_offset: int, *, include_oplus: bool = True) -> bytes:
    """构造兼容 Google Motion Photo v1.0 / MicroVideo / OPPO O-Live 的 XMP XML。"""
    if video_offset <= 0:
        raise ValueError("video_offset must be positive")
    oplus_ns = (
        '\n    xmlns:OpCamera="http://ns.oplus.com/photos/1.0/camera/"' if include_oplus else ""
    )
    oplus_attrs = (
        '\n    OpCamera:MotionPhotoOwner="oplus"\n    OpCamera:OLivePhotoVersion="2"'
        if include_oplus
        else ""
    )
    xml = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:Container="http://ns.google.com/photos/1.0/container/"\n'
        '    xmlns:Item="http://ns.google.com/photos/1.0/container/item/"\n'
        '    xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"'
        f"{oplus_ns}\n"
        '    GCamera:MotionPhoto="1"\n'
        '    GCamera:MotionPhotoVersion="1"\n'
        '    GCamera:MotionPhotoPresentationTimestampUs="0"\n'
        '    GCamera:MicroVideo="1"\n'
        '    GCamera:MicroVideoVersion="1"\n'
        f'    GCamera:MicroVideoOffset="{int(video_offset)}"\n'
        '    GCamera:MicroVideoPresentationTimestampUs="0"'
        f"{oplus_attrs}>\n"
        "   <Container:Directory>\n"
        "    <rdf:Seq>\n"
        '     <rdf:li rdf:parseType="Resource">\n'
        "      <Container:Item\n"
        '        Item:Mime="image/jpeg"\n'
        '        Item:Semantic="Primary"\n'
        '        Item:Length="0"\n'
        '        Item:Padding="0"/>\n'
        "     </rdf:li>\n"
        '     <rdf:li rdf:parseType="Resource">\n'
        "      <Container:Item\n"
        '        Item:Mime="video/mp4"\n'
        '        Item:Semantic="MotionPhoto"\n'
        f'        Item:Length="{int(video_offset)}"\n'
        '        Item:Padding="0"/>\n'
        "     </rdf:li>\n"
        "    </rdf:Seq>\n"
        "   </Container:Directory>\n"
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>"
    )
    return xml.encode("utf-8")


def _build_enriched_exif_segment(existing_exif_payload: Optional[bytes]) -> Optional[bytes]:
    """在 EXIF ExifIFD(0x8769) 中写入 OPPO/一加识别所需的 UserComment(0x9286)。"""
    try:
        from PIL import Image

        exif = Image.Exif()
        if existing_exif_payload:
            try:
                exif.load(existing_exif_payload)
            except Exception:
                exif = Image.Exif()
        exif_ifd = exif.get_ifd(0x8769)
        exif_ifd[0x9286] = _OPLUS_USER_COMMENT
        payload = exif.tobytes()
        if payload and len(payload) + 2 <= 65535:
            return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    except Exception as exc:  # noqa: BLE001
        logger.debug("Build EXIF UserComment skipped: %s", exc)
    if existing_exif_payload and len(existing_exif_payload) + 2 <= 65535:
        return b"\xff\xe1" + struct.pack(">H", len(existing_exif_payload) + 2) + existing_exif_payload
    return None


def inject_motion_photo_metadata(
    jpeg_bytes: bytes,
    video_offset: int,
    *,
    include_oplus: bool = True,
) -> bytes:
    """将 Motion Photo XMP（与可选 EXIF UserComment）无损注入 JPEG APP1 段。"""
    if not _is_jpeg_bytes(jpeg_bytes):
        return jpeg_bytes

    xmp_payload = _XMP_HEADER + build_motion_photo_xmp(video_offset, include_oplus=include_oplus)
    if len(xmp_payload) + 2 > 65535:
        raise ValueError("XMP payload exceeds JPEG APP1 segment limit")
    xmp_segment = b"\xff\xe1" + struct.pack(">H", len(xmp_payload) + 2) + xmp_payload

    leading_app0: List[bytes] = []
    other_segments: List[bytes] = []
    existing_exif_payload: Optional[bytes] = None
    tail_scan_data: Optional[bytes] = None

    pos = 2
    length = len(jpeg_bytes)
    parsed_ok = True
    while pos < length:
        if jpeg_bytes[pos] != 0xFF:
            parsed_ok = False
            break
        while pos < length and jpeg_bytes[pos] == 0xFF:
            pos += 1
        if pos >= length:
            parsed_ok = False
            break
        marker = jpeg_bytes[pos]
        pos += 1
        if marker == 0xDA:  # SOS
            tail_scan_data = b"\xff\xda" + jpeg_bytes[pos:]
            break
        if marker == 0xD9:  # EOI
            tail_scan_data = b"\xff\xd9" + jpeg_bytes[pos:]
            break
        if marker in _STANDALONE_MARKERS:
            other_segments.append(bytes((0xFF, marker)))
            continue
        if pos + 2 > length:
            parsed_ok = False
            break
        seg_len = struct.unpack(">H", jpeg_bytes[pos : pos + 2])[0]
        if seg_len < 2 or pos + seg_len > length:
            parsed_ok = False
            break
        payload = jpeg_bytes[pos + 2 : pos + seg_len]
        raw_segment = bytes((0xFF, marker)) + jpeg_bytes[pos : pos + seg_len]
        pos += seg_len

        if marker == 0xE0 and not leading_app0:
            leading_app0.append(raw_segment)
        elif marker == 0xE1 and payload.startswith(_XMP_HEADER):
            continue
        elif marker == 0xE1 and payload.startswith(_EXIF_HEADER) and existing_exif_payload is None:
            existing_exif_payload = payload
        else:
            other_segments.append(raw_segment)

    if not parsed_ok or tail_scan_data is None:
        return jpeg_bytes[:2] + xmp_segment + jpeg_bytes[2:]

    exif_segment = (
        _build_enriched_exif_segment(existing_exif_payload)
        if include_oplus
        else (
            b"\xff\xe1" + struct.pack(">H", len(existing_exif_payload) + 2) + existing_exif_payload
            if existing_exif_payload
            else None
        )
    )

    parts: List[bytes] = [b"\xff\xd8", *leading_app0]
    if exif_segment:
        parts.append(exif_segment)
    parts.append(xmp_segment)
    parts.extend(other_segments)
    parts.append(tail_scan_data)
    return b"".join(parts)


def parse_motion_photo_offset(data: bytes) -> Optional[int]:
    """从嵌入的 XMP 中解析 MotionPhoto / MicroVideo 视频字节长度。"""
    if not data:
        return None
    head = data[:65536]
    match = _XMP_ITEM_LENGTH_RE.search(head) or _XMP_MICRO_OFFSET_RE.search(head)
    if not match:
        return None
    raw_digits = next((group for group in match.groups() if group), None)
    if not raw_digits:
        return None
    try:
        offset = int(raw_digits)
    except ValueError:
        return None
    return offset if offset > 0 else None


def merge_live_photo_bytes(
    image_bytes: bytes,
    video_bytes: bytes,
    *,
    format_mode: str = DEFAULT_LIVE_PHOTO_FORMAT,
) -> bytes:
    """按指定格式合成单文件动态照片字节。"""
    if not image_bytes:
        raise ValueError("image_bytes is empty")
    if not video_bytes:
        raise ValueError("video_bytes is empty")

    mode = normalize_live_photo_format(format_mode)
    if mode == "android":
        enriched = inject_motion_photo_metadata(image_bytes, len(video_bytes), include_oplus=True)
        return enriched + video_bytes

    duration_ms = _read_mp4_duration_ms(video_bytes)
    trailer = build_huawei_trailer(len(video_bytes), duration_ms=duration_ms)
    if mode == "huawei":
        return image_bytes + video_bytes + trailer

    xmp_offset = len(video_bytes) + len(trailer)
    enriched = inject_motion_photo_metadata(image_bytes, xmp_offset, include_oplus=True)
    return enriched + video_bytes + trailer


def merge_live_photo_files(
    image_path: Path,
    video_path: Path,
    output_path: Path,
    *,
    convert_still_to_jpeg: bool = True,
    format_mode: str = DEFAULT_LIVE_PHOTO_FORMAT,
) -> Optional[Path]:
    """把静态图与视频合并为动态照片文件，返回输出路径或 None。

    若静态图不是 JPEG（如 WebP），默认用 Pillow 转成高质量 JPEG，保证
    各厂商手机相册均能识别；转换失败时退回原字节拼接。
    """
    try:
        image_bytes = image_path.read_bytes()
        video_bytes = video_path.read_bytes()
        if not image_bytes or not video_bytes:
            logger.warning("Live photo merge skipped: empty input %s / %s", image_path, video_path)
            return None

        if convert_still_to_jpeg and not _is_jpeg_bytes(image_bytes):
            converted = _convert_to_jpeg(image_bytes)
            if converted:
                image_bytes = converted

        merged = merge_live_photo_bytes(image_bytes, video_bytes, format_mode=format_mode)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(merged)
        logger.info(
            "Merged live photo (%s): %s (still=%d bytes, video=%d bytes)",
            normalize_live_photo_format(format_mode),
            output_path,
            len(image_bytes),
            len(video_bytes),
        )
        return output_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live photo merge failed: %s", exc)
        return None


def verify_live_photo(path: Path) -> Tuple[bool, Optional[str], Optional[int]]:
    """校验动态照片格式（``LIVE_`` 尾标或 XMP Motion Photo 偏移）；返回 (ok, tag, mp4_size)。"""
    try:
        data = path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Verify live photo read failed: %s", exc)
        return False, None, None
    parsed = parse_footer(data)
    if parsed is not None:
        footer_text, live_val = parsed
        span = extract_huawei_mp4_span(data)
        if span is not None:
            return True, footer_text, span[1] - span[0]
        return False, footer_text, live_val

    motion_offset = parse_motion_photo_offset(data)
    if motion_offset is not None and 0 < motion_offset < len(data):
        return True, "MOTION_PHOTO", motion_offset
    return False, None, None


def _is_jpeg_bytes(data: bytes) -> bool:
    return len(data) > 3 and data[:3] == b"\xff\xd8\xff"


def _convert_to_jpeg(data: bytes) -> Optional[bytes]:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=92)
            return buffer.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Convert still to JPEG failed: %s", exc)
        return None


def read_video_size_from_footer(path: Path) -> Optional[int]:
    """读取嵌入视频的字节长度（兼容华为 60B/40B/20B 尾标与 XMP MotionPhoto）。"""
    try:
        data = path.read_bytes()
    except Exception:
        return None
    span = extract_huawei_mp4_span(data)
    if span is not None:
        return span[1] - span[0]
    return parse_motion_photo_offset(data)
