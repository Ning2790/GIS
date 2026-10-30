"""E2E 测试库准备：独立 SQLite 临时库 + 迁移 + 最小种子数据。

由 Playwright 的 globalSetup 调用（也可手动跑，见 e2e/README.md）：
    cd backend && uv run python ../e2e/prepare_db.py

设计：
- 库文件固定在 `e2e/.tmp/e2e.db`，每次重建——与开发库 / 演示库**完全隔离**；
- 迁移走 alembic（顺带验证迁移链在 SQLite 上可用，与 CI 的 PG 检查互补）；
- 种子**不依赖 MinIO / Redis**：管理员、商户、商品直接写库；景点与路线复用仓库既有 seed 脚本。
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DB_FILE = ROOT / "e2e" / ".tmp" / "e2e.db"

os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE.as_posix()}"
os.environ.setdefault("REDIS_URL", "")  # 隔离：不接开发 Redis（限流 / 闸门自动降级）
os.environ.setdefault("MINIO_ENDPOINT", "")  # 隔离：E2E 不用文件上传
os.environ.setdefault("WEATHER_PROVIDER", "mock")  # 采集不触发外网

sys.path.insert(0, str(BACKEND))

ADMIN = {"phone": "13800000000", "password": "admin123456", "nickname": "E2E 管理员"}
MERCHANT = {"phone": "13800000088", "password": "Demo123456", "nickname": "E2E 商户"}
PRODUCTS = [("E2E 牦牛肉干", 138, 50), ("E2E 黑枸杞礼盒", 88, 50)]


def main() -> None:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    DB_FILE.unlink(missing_ok=True)

    # 1) 迁移（alembic 脚本位置用绝对路径，允许从任意工作目录调用）
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(cfg, "head")

    # 2) 账号与商品（直接写库，不经过需审核 / 需对象存储的路径）
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.modules.shop.models import Product, ProductStatus
    from app.modules.users.models import User, UserRole, UserStatus

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.phone == ADMIN["phone"])) is None:
            db.add(
                User(
                    phone=ADMIN["phone"],
                    password_hash=hash_password(ADMIN["password"]),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                    nickname=ADMIN["nickname"],
                )
            )
        merchant = db.scalar(select(User).where(User.phone == MERCHANT["phone"]))
        if merchant is None:
            merchant = User(
                phone=MERCHANT["phone"],
                password_hash=hash_password(MERCHANT["password"]),
                role=UserRole.MERCHANT,
                status=UserStatus.ACTIVE,
                nickname=MERCHANT["nickname"],
            )
            db.add(merchant)
            db.flush()
        for name, price, stock in PRODUCTS:
            if db.scalar(select(Product).where(Product.name == name)) is None:
                db.add(
                    Product(
                        merchant_id=merchant.id,
                        name=name,
                        description="E2E 演示数据",
                        price=price,
                        stock=stock,
                        status=ProductStatus.ON_SALE,
                    )
                )
        db.commit()

    # 3) 景点与路线（复用既有脚本：纯数据库写入）
    for script in ("seed_travel.py", "seed_routes.py"):
        subprocess.run(
            [sys.executable, f"scripts/{script}"],
            cwd=BACKEND,
            check=True,
            env=os.environ.copy(),
        )

    print(f"[e2e] 测试库已就绪：{DB_FILE}")
    print(f"[e2e] 账号：管理员 {ADMIN['phone']} / {ADMIN['password']}；商户 {MERCHANT['phone']} / {MERCHANT['password']}")


if __name__ == "__main__":
    main()
