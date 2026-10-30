"""生成商城演示商品图（一次性脚本，产物提交到 scripts/seed_assets/）。

用法（在 backend 目录下）：
    uv run --with pillow python scripts/make_seed_images.py

说明：Pillow 只是**生成演示图**的一次性依赖（不进项目依赖）；生成好的 PNG 已提交，
`seed_shop.py` 直接读取上传，不再需要 Pillow。样式：品牌色渐变底 + 商品名 + 副标题。
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = BACKEND_ROOT / "scripts" / "seed_assets"

WIDTH, HEIGHT = 800, 600
# 字体：Windows 微软雅黑（本机生成用；产物为 PNG，其他机器不需要字体）
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]

# (文件名, 商品名, 副标题, 顶部色, 底部色)
IMAGES: list[tuple[str, str, str, tuple[int, int, int], tuple[int, int, int]]] = [
    ("product_beef.png", "祁连山牦牛肉干", "青海特产 · 250g×2 袋", (127, 29, 29), (69, 10, 10)),
    ("product_wolfberry.png", "柴达木黑枸杞", "青海特产 · 100g 礼盒", (76, 29, 149), (30, 27, 75)),
    (
        "product_barley_wine.png",
        "互助青稞酒",
        "青海特产 · 52 度 500ml",
        (180, 83, 9),
        (120, 53, 15),
    ),
    (
        "product_rapeseed_oil.png",
        "门源高原菜籽油",
        "青海特产 · 5L 小榨",
        (202, 138, 4),
        (146, 64, 14),
    ),
    (
        "product_snow_chrysanthemum.png",
        "青海雪菊",
        "青海特产 · 80g 罐装",
        (15, 118, 110),
        (19, 78, 74),
    ),
    ("product_saffron.png", "藏红花", "青海特产 · 5g 特级", (190, 24, 93), (131, 24, 67)),
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    raise SystemExit("未找到中文字体（msyh/simhei），请在 Windows 上运行本脚本")


def _vertical_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
        draw.line([(0, y), (WIDTH, y)], fill=color)
    return image


def _centered(draw: ImageDraw.ImageDraw, text: str, font, y: int, fill) -> None:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (right - left)) / 2 - left, y), text, font=font, fill=fill)


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    name_font = _font(64)
    sub_font = _font(28)
    for filename, name, subtitle, top, bottom in IMAGES:
        image = _vertical_gradient(top, bottom)
        draw = ImageDraw.Draw(image)
        # 顶部细高光条 + 底部品牌条，增加一点层次
        draw.rectangle([(0, 0), (WIDTH, 6)], fill=(255, 255, 255, 40))
        _centered(draw, name, name_font, 240, (255, 255, 255))
        _centered(draw, subtitle, sub_font, 336, (255, 255, 255))
        image.save(ASSETS_DIR / filename, "PNG", optimize=True)
        print(f"已生成 {filename}")
    print(f"共 {len(IMAGES)} 张，输出目录：{ASSETS_DIR}")


if __name__ == "__main__":
    main()
