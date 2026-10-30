"""写入商城演示商品（幂等，可重复执行）。

用法（在 backend 目录下）：
    uv run python scripts/seed_shop.py

- 复用演示商户（13800000088，不存在则创建，密码 Demo123456）；
- 按商品名称去重：已存在则更新价格 / 库存 / 描述（演示数据以本脚本为准）；
- 商品主图：从 scripts/seed_assets/ 读取演示图，经 files 模块上传为公开图片
  （MinIO 不可用时跳过并提示，不影响商品写入）。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core import cache  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.files import service as files_service  # noqa: E402
from app.modules.shop.models import Product, ProductStatus  # noqa: E402
from app.modules.users.models import User, UserRole, UserStatus  # noqa: E402

DEMO_PHONE = "13800000088"
DEMO_PASSWORD = "Demo123456"
ASSETS_DIR = BACKEND_ROOT / "scripts" / "seed_assets"

DEMO_PRODUCTS: list[dict] = [
    {
        "name": "祁连山牦牛肉干（250g×2 袋）",
        "image": "product_beef.png",
        "price": 138,
        "stock": 500,
        "description": (
            "选用祁连山牧场散养牦牛后腿肉，风干工艺、肉质紧实，独立小包装便于携带与分享。"
        ),
    },
    {
        "name": "柴达木黑枸杞（100g 礼盒）",
        "image": "product_wolfberry.png",
        "price": 168,
        "stock": 300,
        "description": "柴达木盆地野生黑枸杞，花青素含量高；礼盒装适合馈赠，附冲泡说明。",
    },
    {
        "name": "互助青稞酒（52 度 500ml）",
        "image": "product_barley_wine.png",
        "price": 98,
        "stock": 800,
        "description": "青稞纯粮酿造，口感醇厚；青海本地经典名酒，聚餐与伴手礼皆宜。",
    },
    {
        "name": "门源高原菜籽油（5L 小榨）",
        "image": "product_rapeseed_oil.png",
        "price": 129,
        "stock": 400,
        "description": "高原油菜籽物理压榨，浓香扑鼻；适合日常烹饪，可提供质检报告。",
    },
    {
        "name": "青海雪菊（80g 罐装）",
        "image": "product_snow_chrysanthemum.png",
        "price": 88,
        "stock": 600,
        "description": "高原雪菊茶，汤色金黄、香气清甜；罐装防潮，办公室与居家常备。",
    },
    {
        "name": "藏红花（5g 特级）",
        "image": "product_saffron.png",
        "price": 258,
        "stock": 200,
        "description": "特级藏红花花丝，色泽深红；小瓶避光装，建议阴凉干燥处保存。",
    },
]


DEMO_PRODUCTS_IMAGE = {item["name"]: item.get("image", "") for item in DEMO_PRODUCTS}


def _upload_image(db, merchant, product) -> bool:
    """给商品补演示主图（已有图 / 资源缺失 / 存储不可用时跳过），返回是否新上传。"""
    if product.image_file_id is not None:
        return False
    asset_path = ASSETS_DIR / DEMO_PRODUCTS_IMAGE.get(product.name, "")
    if not asset_path.is_file():
        return False
    record = files_service.upload(
        db,
        merchant,
        filename=asset_path.name,
        content_type="image/png",
        data=asset_path.read_bytes(),
        public=True,
    )
    product.image_file_id = record.id
    return True


def main() -> None:
    created = 0
    updated = 0
    imaged = 0
    image_skipped = False
    with SessionLocal() as db:
        merchant = db.scalar(select(User).where(User.phone == DEMO_PHONE))
        if merchant is None:
            merchant = User(
                phone=DEMO_PHONE,
                password_hash=hash_password(DEMO_PASSWORD),
                role=UserRole.MERCHANT,
                status=UserStatus.ACTIVE,
                nickname="演示商户",
            )
            db.add(merchant)
            db.flush()

        for item in DEMO_PRODUCTS:
            product = db.scalar(select(Product).where(Product.name == item["name"]))
            if product is not None:
                product.price = item["price"]
                product.stock = item["stock"]
                product.description = item["description"]
                product.status = ProductStatus.ON_SALE
                updated += 1
            else:
                product = Product(
                    merchant_id=merchant.id,
                    name=item["name"],
                    description=item["description"],
                    price=item["price"],
                    stock=item["stock"],
                    status=ProductStatus.ON_SALE,
                )
                db.add(product)
                created += 1
            db.flush()  # 拿到 product.id 后再补图
            try:
                if _upload_image(db, merchant, product):
                    imaged += 1
            except Exception as exc:  # MinIO 未起 / 未配置：跳过图片，不影响商品数据
                image_skipped = True
                print(f"  ⚠ 商品图上传跳过（{exc}）")
        db.commit()

    # 商品列表有 60s 读缓存（P1）：直接写库后 bump 版本让缓存立即失效
    cache.bump_version("shop:products")
    print(f"已写入 {created} 个新商品、更新 {updated} 个商品、补图 {imaged} 张（演示数据）。")
    if image_skipped:
        print("提示：部分商品图未上传（对象存储不可用）；起 MinIO 后重跑本脚本即可补齐。")


if __name__ == "__main__":
    main()
