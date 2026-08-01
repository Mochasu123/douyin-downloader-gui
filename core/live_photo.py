"""Live Photo 合并工具：JPG + MP4 拼接为华为/通用可识别的动态照片文件。

社区与第三方工具已验证的通用格式：图片字节 + 视频字节 + 尾部 20 字节
``LIVE_`` 标记，其中 ``XXXX`` 为视频字节长度的 15 位十进制数字。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from utils.logger import setup_logger

logger = setup_logger("LivePhoto")

_FOOTER_PREFIX = b"LIVE_"
_FOOTER_LENGTH = 20
_SIZE_DIGITS = _FOOTER_LENGTH - len(_FOOTER_PREFIX)


def build_footer(video_size: int) -> bytes:
    """构造尾部 20 字节：``LIVE_`` + 15 位十进制视频长度。"""
    if video_size < 0:
        raise ValueError("video_size must be non-negative")
    return _FOOTER_PREFIX + f"{int(video_size):0{_SIZE_DIGITS}d}".encode("ascii")


def parse_footer(data: bytes) -> Optional[Tuple[str, int]]:
    """解析文件末尾 20 字节；非 Live Photo 格式时返回 None。"""
    if not data or len(data) < _FOOTER_LENGTH:
        return None
    footer = data[-_FOOTER_LENGTH:]
    if not footer.startswith(_FOOTER_PREFIX):
        return None
    size_text = footer[len(_FOOTER_PREFIX):].decode("ascii", errors="replace")
    try:
        video_size = int(size_text)
    except ValueError:
        return None
    return size_text, video_size


def merge_live_photo_bytes(image_bytes: bytes, video_bytes: bytes) -> bytes:
    """拼接图片 + 视频 + 尾部标记，返回合并后的动态照片字节。"""
    if not image_bytes:
        raise ValueError("image_bytes is empty")
    if not video_bytes:
        raise ValueError("video_bytes is empty")
    return image_bytes + video_bytes + build_footer(len(video_bytes))


def merge_live_photo_files(
    image_path: Path,
    video_path: Path,
    output_path: Path,
    *,
    convert_still_to_jpeg: bool = True,
) -> Optional[Path]:
    """把静态图与视频合并为动态照片文件，返回输出路径或 None。

    若静态图不是 JPEG（如 WebP），默认用 Pillow 转成高质量 JPEG，保证
    华为/手机图库能识别；转换失败时退回原字节拼接。
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

        merged = merge_live_photo_bytes(image_bytes, video_bytes)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(merged)
        logger.info("Merged live photo: %s (still=%d bytes, video=%d bytes)",
                    output_path, len(image_bytes), len(video_bytes))
        return output_path
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live photo merge failed: %s", exc)
        return None


def verify_live_photo(path: Path) -> Tuple[bool, Optional[str], Optional[int]]:
    """校验文件尾部标记与视频长度；返回 (ok, footer, video_size)。"""
    try:
        data = path.read_bytes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Verify live photo read failed: %s", exc)
        return False, None, None
    parsed = parse_footer(data)
    if parsed is None:
        return False, None, None
    footer, video_size = parsed
    if video_size > len(data) - _FOOTER_LENGTH:
        return False, footer, video_size
    return True, footer, video_size


def _is_jpeg_bytes(data: bytes) -> bool:
    return len(data) > 3 and data[:3] == b"\xff\xd8\xff"


def _convert_to_jpeg(data: bytes) -> Optional[bytes]:
    try:
        from PIL import Image
        import io

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
    """读取尾部声明的视频长度（用于快速校验）。"""
    try:
        data = path.read_bytes()
    except Exception:
        return None
    parsed = parse_footer(data)
    return parsed[1] if parsed else None
