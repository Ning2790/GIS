"""图片处理（Pillow）：上传时压缩 + 生成缩略图（需求 4.1）。

纯函数模块（不碰数据库 / 对象存储），便于单测。

- 只处理**可解码的静态图片**；解析失败（伪造头 / 损坏 / 解码炸弹）、
  **动图**（动画 WebP / APNG，重编码只会留第一帧）、超过像素上限的大图
  一律返回 None，由调用方原样入库——优化失败绝不能让上传失败。
- 保持原格式族（JPEG→JPEG、PNG→PNG、WebP→WebP）：避免扩展名 / Content-Type 与
  实际内容不一致带来的兼容问题；仅**缩略图**在 PNG 无透明通道时转 JPEG
  （照片型 PNG 的缩略图体积差一个量级，透明度又用不上）。
- 重编码时按 EXIF 方向固化像素，并丢弃元数据（EXIF / GPS 不外泄）。
- 缩放只缩不放（长边超过上限才等比缩小）；压缩后不比原图小就保留原图，
  小图 / 已优化过的图不做无意义重编码。
- 大 JPEG 先 `draft` 按需解码到接近目标尺寸（解码内存 / 耗时降一个量级）；
  16 位整数 / 浮点灰度图归一为 8 位（Pillow 的缩放快路径与 PNG 存 16 位都已不支持）。
"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

_EXTENSION_BY_TYPE = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

# 解码炸弹防线：源图像素上限。校验在解码前进行（Image.open 是惰性的），
# 避免几 MB 的构造文件在内存里解出几十亿像素。超过即放弃优化、原样入库。
MAX_SOURCE_PIXELS = 40_000_000

# 需要归一为 8 位灰度的「技术性」模式（见 _normalize_mode）
_WIDE_MODES = frozenset({"I", "I;16", "I;16B", "I;16L", "I;16N", "F"})


@dataclass(frozen=True)
class ProcessedImage:
    """压缩 + 缩略图结果（size 为入库对象字节数，original_size 为上传原始字节数）。"""

    data: bytes
    size: int
    original_size: int
    thumbnail: bytes | None
    thumbnail_content_type: str | None


def extension_for(content_type: str) -> str:
    """图片类型对应的扩展名（对象键用）。"""
    return _EXTENSION_BY_TYPE.get(content_type, "")


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA", "PA"):
        return True
    return image.mode == "P" and "transparency" in image.info


def _normalize_mode(image: Image.Image) -> Image.Image:
    """把 Pillow 的「技术性」模式归一为 8 位（16 位 / 浮点灰度 → L）。

    16 位整数 / 浮点模式既不被 Pillow 的缩放快路径支持，PNG 存 16 位也已被
    Pillow 标记废弃（13.0 移除）；本功能面向展示图（商品图 / 资质），按 8 位灰度
    处理即可，避免「合法图片被判为不可解码」。
    """
    if image.mode in _WIDE_MODES:
        return image.convert("L")
    return image


def _save_params(
    image: Image.Image, content_type: str, quality: int, *, allow_jpeg_fallback: bool
) -> tuple[str, str, dict]:
    """返回 (Pillow 格式, 产物 Content-Type, 保存参数)。"""
    jpeg = ("JPEG", "image/jpeg", {"quality": quality, "optimize": True, "progressive": True})
    if content_type == "image/jpeg":
        return jpeg
    if content_type == "image/webp":
        return ("WEBP", "image/webp", {"quality": quality, "method": 4})
    # PNG：有透明通道必须留 PNG；无透明且允许回退时转 JPEG（体积小得多）
    if allow_jpeg_fallback and not _has_alpha(image):
        return jpeg
    return ("PNG", "image/png", {"optimize": True})


def _shrink(image: Image.Image, edge: int) -> Image.Image:
    """等比缩到长边 ≤ edge（只缩不放）。

    用 Pillow 的 reduce 快路径（reducing_gap，大图缩放快得多），但该路径不支持
    16 位整数 / 浮点模式——这类模式已在上游归一为 8 位（见 _normalize_mode），
    这里再兜一次：失败就退回无快路径的 resize。
    """
    target = image.copy()
    try:
        target.thumbnail((edge, edge), Image.LANCZOS)
    except ValueError:
        target = image.copy()
        target.thumbnail((edge, edge), Image.LANCZOS, reducing_gap=None)
    return target


def _encode(
    image: Image.Image, edge: int, content_type: str, quality: int, *, allow_jpeg_fallback: bool
) -> tuple[bytes, str]:
    """等比缩到长边 ≤ edge（不放大）并按目标格式重编码，返回 (字节, Content-Type)。"""
    target = _shrink(image, edge)
    fmt, out_type, params = _save_params(
        target, content_type, quality, allow_jpeg_fallback=allow_jpeg_fallback
    )
    if fmt == "JPEG" and target.mode != "RGB":
        target = target.convert("RGB")
    buffer = BytesIO()
    target.save(buffer, format=fmt, **params)
    return buffer.getvalue(), out_type


def process(
    data: bytes,
    content_type: str,
    *,
    max_edge: int,
    jpeg_quality: int,
    thumbnail_edge: int,
) -> ProcessedImage | None:
    """压缩原图并生成缩略图；不可处理返回 None（非图片 / 解码失败 / 超像素上限 / 动图）。

    返回 None 一律由调用方原样入库——**优化失败绝不能让上传失败**，
    因此这里的兜底捕获是刻意的宽口径（含 MemoryError 等运行时错误）。
    """
    if content_type not in IMAGE_CONTENT_TYPES:
        return None
    original_size = len(data)
    try:
        with Image.open(BytesIO(data)) as source:
            # 先看尺寸再解码：超大图直接放弃优化（省内存，也避开 Pillow 的解码炸弹告警）
            if source.width * source.height > MAX_SOURCE_PIXELS:
                return None
            # 动图（动画 WebP / APNG）：重编码只会留第一帧，等于**静默销毁动画**——
            # 原样入库（列表页缩略图随之回退原图，与「不阻断上传」一致）
            if getattr(source, "is_animated", False):
                return None
            # 大 JPEG 先 draft：按需解码到接近目标尺寸（解码内存与时间都降一个量级）
            longest = max(max_edge, thumbnail_edge)
            if longest > 0:
                source.draft("RGB", (longest, longest))
            source.load()
            # 手机照片带方向标记：按 EXIF 把像素转正，产物不再保留元数据
            image = ImageOps.exif_transpose(source) or source
            image.load()
            image = _normalize_mode(image)

            stored = data
            if max_edge > 0:
                candidate, _ = _encode(
                    image, max_edge, content_type, jpeg_quality, allow_jpeg_fallback=False
                )
                if len(candidate) < original_size:  # 没有更小就不折腾，存原图
                    stored = candidate

            thumbnail = None
            thumbnail_content_type = None
            if thumbnail_edge > 0:
                thumbnail, thumbnail_content_type = _encode(
                    image, thumbnail_edge, content_type, jpeg_quality, allow_jpeg_fallback=True
                )
    except Exception:  # noqa: BLE001 - 见 docstring：优化失败不能阻断上传
        return None
    return ProcessedImage(
        data=stored,
        size=len(stored),
        original_size=original_size,
        thumbnail=thumbnail,
        thumbnail_content_type=thumbnail_content_type,
    )
