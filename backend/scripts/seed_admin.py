"""创建首个管理员账号（幂等，可重复执行）。

用法（在 backend 目录下）：
    uv run python scripts/seed_admin.py

可用环境变量覆盖默认值：ADMIN_PHONE / ADMIN_PASSWORD / ADMIN_NICKNAME。
生产环境务必修改默认密码。审核接口（/api/v1/admin/reviews）需要管理员身份才能调用。
"""

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.errors import ConflictError  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.users import service as users_service  # noqa: E402


def main() -> None:
    phone = os.getenv("ADMIN_PHONE", "13800000000")
    password = os.getenv("ADMIN_PASSWORD", "admin123456")
    nickname = os.getenv("ADMIN_NICKNAME", "平台管理员")

    admin_id = None
    with SessionLocal() as db:
        try:
            user = users_service.create_admin(db, phone=phone, password=password, nickname=nickname)
        except ConflictError:
            print(f"管理员账号已存在，跳过：{phone}")
            return
        # 必须在会话内取 id：会话关闭后对象即 detached，读属性会触发 DetachedInstanceError
        # （空库首次运行才会走到这里，此前一直被「管理员已存在」的早退路径掩盖）
        admin_id = user.id

    print(f"已创建管理员账号：{phone}（id={admin_id}，请尽快修改默认密码）")


if __name__ == "__main__":
    main()
