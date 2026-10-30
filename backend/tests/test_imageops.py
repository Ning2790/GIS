"""imageops 单测：压缩 / 缩略图 / 格式与透明度处理 / 失败原样返回。"""

from io import BytesIO

import pytest
from PIL import Image

from app.modules.files import imageops

# 长边超上限的"手机照片"（JPEG，噪点保证体积可观）
BIG_EDGE = 2400


def _image_bytes(
    size: tuple[int, int],
    *,
    mode: str = "RGB",
    fmt: str = "JPEG",
    noisy: bool = True,
    **save_kwargs,
) -> bytes:
    """生成一张可解码的图片（噪点让 JPEG 压缩有真实收益）。"""
    image = Image.new(mode, size, (120, 140, 160) if mode != "RGBA" else (120, 140, 160, 128))
    if noisy:
        pixels = image.load()
        for x in range(0, size[0], 3):
            for y in range(0, size[1], 3):
                pixels[x, y] = (
                    (x % 256, y % 256, (x + y) % 256)
                    if mode != "RGBA"
                    else (
                        x % 256,
                        y % 256,
                        (x + y) % 256,
                        200,
                    )
                )
    buffer = BytesIO()
    image.save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def _process(data: bytes, content_type: str, **overrides):
    params = {"max_edge": 1600, "jpeg_quality": 82, "thumbnail_edge": 400}
    params.update(overrides)
    return imageops.process(data, content_type, **params)


def test_large_jpeg_downscaled_and_thumbnail_generated() -> None:
    data = _image_bytes((BIG_EDGE, BIG_EDGE))
    result = _process(data, "image/jpeg")
    assert result is not None

    # 原图缩到长边上限、体积明显变小、原始大小如实记录
    with Image.open(BytesIO(result.data)) as stored:
        assert max(stored.size) == 1600
    assert result.size < result.original_size == len(data)

    # 缩略图长边 ≤ 上限，且比原图小
    assert result.thumbnail is not None
    with Image.open(BytesIO(result.thumbnail)) as thumb:
        assert max(thumb.size) == 400
    assert result.thumbnail_content_type == "image/jpeg"
    assert len(result.thumbnail) < result.size


def test_small_image_never_grows() -> None:
    """小图：不放大；重编码不划算就保留原图（绝不把文件变大）。"""
    data = _image_bytes((120, 80))
    result = _process(data, "image/jpeg")
    assert result is not None
    assert result.size <= result.original_size
    with Image.open(BytesIO(result.data)) as stored:
        assert stored.size == (120, 80)  # 只缩不放
    assert result.thumbnail is not None  # 缩略图仍会生成（列表页统一走缩略图地址）


def test_keep_original_when_reencode_is_bigger(monkeypatch: pytest.MonkeyPatch) -> None:
    """压缩产出更大时保留原图（不为了「压过」而把文件变大）。"""
    data = _image_bytes((200, 150))

    def _bigger(*_args, **_kwargs) -> tuple[bytes, str]:
        return data + b"x" * 500, "image/jpeg"

    monkeypatch.setattr(imageops, "_encode", _bigger)
    result = _process(data, "image/jpeg", thumbnail_edge=0)
    assert result is not None
    assert result.data == data
    assert result.size == result.original_size == len(data)


def test_no_upscale_when_smaller_than_thumbnail_edge() -> None:
    data = _image_bytes((64, 48))
    result = _process(data, "image/jpeg")
    assert result is not None
    with Image.open(BytesIO(result.thumbnail or b"")) as thumb:
        assert thumb.size == (64, 48)  # 不放大小图


def test_png_with_alpha_keeps_png_everywhere() -> None:
    data = _image_bytes((900, 600), mode="RGBA", fmt="PNG")
    result = _process(data, "image/png")
    assert result is not None
    assert result.thumbnail_content_type == "image/png"  # 透明通道不能丢
    with Image.open(BytesIO(result.data)) as stored:
        assert stored.format == "PNG"
    with Image.open(BytesIO(result.thumbnail or b"")) as thumb:
        assert thumb.format == "PNG"


def test_opaque_png_thumbnail_converts_to_jpeg() -> None:
    """无透明通道的 PNG（截图 / 照片）：原图仍存 PNG，缩略图转 JPEG 省体积。"""
    data = _image_bytes((1200, 900), mode="RGB", fmt="PNG")
    result = _process(data, "image/png")
    assert result is not None
    with Image.open(BytesIO(result.data)) as stored:
        assert stored.format == "PNG"
    assert result.thumbnail_content_type == "image/jpeg"
    with Image.open(BytesIO(result.thumbnail or b"")) as thumb:
        assert thumb.format == "JPEG"


def test_undecodable_bytes_return_none() -> None:
    """伪造头 / 损坏内容：返回 None，由调用方原样入库（优化失败不能阻断上传）。"""
    fake_png = b"\x89PNG\r\n\x1a\n" + b"0" * 64  # 只像 PNG，解不开
    assert _process(fake_png, "image/png") is None
    assert _process(b"\xff\xd8\xff\xe0" + b"junk", "image/jpeg") is None


def test_non_image_type_return_none() -> None:
    assert _process(b"%PDF-1.4 fake", "application/pdf") is None
    assert _process(b"", "application/pdf") is None


def test_animated_image_skipped() -> None:
    """动图（动画 WebP / APNG）：重编码只会留第一帧，宁可原样入库也不静默销毁动画。"""
    frames = [Image.new("RGB", (120, 90), color) for color in ((200, 40, 40), (40, 40, 200))]
    for fmt in ("WEBP", "PNG"):
        buffer = BytesIO()
        frames[0].save(buffer, format=fmt, save_all=True, append_images=frames[1:], duration=200)
        content_type = "image/webp" if fmt == "WEBP" else "image/png"
        with Image.open(BytesIO(buffer.getvalue())) as check:
            assert check.n_frames > 1  # 确认构造出了真动图
        assert _process(buffer.getvalue(), content_type) is None


def test_16bit_grayscale_png_processed() -> None:
    """16 位整数灰度 PNG（扫描件常见）：归一为 8 位后照常压缩 + 生成缩略图。"""
    buffer = BytesIO()
    Image.new("I;16", (1600, 1200), 3000).save(buffer, format="PNG")
    data = buffer.getvalue()

    result = _process(data, "image/png")
    assert result is not None  # 不再被当成「不可解码」
    assert result.thumbnail is not None
    with Image.open(BytesIO(result.data)) as stored:
        assert stored.mode == "L"
        assert max(stored.size) == 1600  # 4 倍缩放在旧实现会抛 ValueError
    with Image.open(BytesIO(result.thumbnail or b"")) as thumb:
        assert max(thumb.size) == 400


def test_pixel_bomb_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """超过像素上限的图直接放弃优化（不抛异常、不进内存里解码）。"""
    data = _image_bytes((300, 200))
    monkeypatch.setattr(imageops, "MAX_SOURCE_PIXELS", 100)  # 300×200 = 60000 > 100
    assert _process(data, "image/jpeg") is None


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [("image/jpeg", ".jpg"), ("image/png", ".png"), ("image/webp", ".webp")],
)
def test_extension_for(content_type: str, expected: str) -> None:
    assert imageops.extension_for(content_type) == expected


def test_settings_can_disable_everything() -> None:
    """max_edge=0 且 thumbnail_edge=0：只登记原始大小，不做任何重编码。"""
    data = _image_bytes((2400, 2400))
    result = _process(data, "image/jpeg", max_edge=0, thumbnail_edge=0)
    assert result is not None
    assert result.data == data
    assert result.thumbnail is None
    assert result.original_size == len(data)
