"""创建演示账号：演示商户 + 演示游客（幂等，可重复执行）。

用法（在 backend 目录下）：
    uv run python scripts/seed_demo_accounts.py

背景：`seed_shop.py` 只负责**商户**（13800000088，商品挂它名下），演示脚本里
「演示游客」（13900001111）此前没有脚本创建——重建库后账号就没了，演示第一步就登不进去。
本脚本把两个演示账号统一补齐（管理员见 `seed_admin.py`）。

账号与 `docs/演示脚本.md` 的「演示账号」表一致（含**待审核企业**——它保持
pending_review 状态，登录会被拦截，正是资质审核演示要看的行为）；只创建不修改
（已存在则跳过，不会把改过的密码重置回去）。**订单 / 售后仍由演示现场操作产生**（不预置）。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.users.models import User, UserRole, UserStatus  # noqa: E402

# (手机号, 密码, 角色, 昵称, 账号状态)
DEMO_ACCOUNTS: list[tuple[str, str, str, str, str]] = [
    ("13800000088", "Demo123456", UserRole.MERCHANT, "演示商户", UserStatus.ACTIVE),
    ("13900001111", "test123456", UserRole.TOURIST, "演示游客", UserStatus.ACTIVE),
    # 资质审核演示用：**保持待审核**（登录会被拦截，属预期行为，见 docs/演示脚本.md）
    ("13900002222", "demo123456", UserRole.ENTERPRISE, "待审核企业", UserStatus.PENDING_REVIEW),
]


def main() -> None:
    created = skipped = 0
    with SessionLocal() as db:
        for phone, password, role, nickname, status in DEMO_ACCOUNTS:
            existing = db.scalar(select(User).where(User.phone == phone))
            if existing is not None:
                skipped += 1
                continue
            db.add(
                User(
                    phone=phone,
                    password_hash=hash_password(password),
                    role=role,
                    status=status,
                    nickname=nickname,
                )
            )
            created += 1
        db.commit()
    print(f"演示账号：新增 {created} 个、已存在跳过 {skipped} 个（共 {len(DEMO_ACCOUNTS)} 个）。")
    if created:
        print("默认密码仅用于本地演示，公开部署前请修改。")


if __name__ == "__main__":
    main()
