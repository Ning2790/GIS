"""dashboard 模块路由：控制台首页概览（商户 / 企业 / 管理员）。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import DbSession, require_roles
from app.core import metrics
from app.core.response import ok
from app.modules.dashboard import service
from app.modules.users.models import User, UserRole

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# 控制台首页：商户 / 企业 / 管理员可见（游客端无控制台）
ConsoleUser = Annotated[
    User, Depends(require_roles(UserRole.MERCHANT, UserRole.ENTERPRISE, UserRole.ADMIN))
]
# 监控指标是平台级数据（不分商户）：仅管理员
AdminUser = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("/summary", summary="控制台首页概览（按角色返回不同字段）")
def get_summary(db: DbSession, viewer: ConsoleUser) -> dict:
    summary = service.get_summary(db, viewer)
    return ok(summary.model_dump(mode="json"))


@router.get("/metrics", summary="运行指标汇总（仅管理员；与 /metrics 同源）")
def get_metrics(admin: AdminUser) -> dict:
    """概览页监控卡片的数据源：请求量 / P95 延迟 / 限流命中 / 排队拒绝 / 队列长度。

    指标是**平台级**的（不分商户），因此仅管理员可见。
    """
    return ok(metrics.snapshot())
