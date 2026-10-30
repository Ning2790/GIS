"""v1 路由聚合点。

新增模块时，在此挂载该模块的 router。本文件属于**公共层**，改动需走 PR 评审，
以免多人同时修改产生冲突。
"""

from fastapi import APIRouter

from app.core.response import ok
from app.modules.admin.router import router as admin_router
from app.modules.ai.router import router as ai_router
from app.modules.auth.router import router as auth_router
from app.modules.b2b.router import router as b2b_router
from app.modules.cs.router import router as cs_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.files.router import router as files_router
from app.modules.gear.router import router as gear_router
from app.modules.map.router import router as map_router
from app.modules.notifications.router import router as notifications_router
from app.modules.shop.router import router as shop_router
from app.modules.travel.router import router as travel_router
from app.modules.users.router import router as users_router

api_router = APIRouter()


@api_router.get("/health", tags=["meta"], summary="健康检查")
def health() -> dict:
    """探活接口：前端与运维据此判断后端是否可用。"""
    return ok({"status": "healthy"})


for _module_router in (
    auth_router,
    users_router,
    travel_router,
    map_router,
    gear_router,
    shop_router,
    b2b_router,
    ai_router,
    cs_router,
    dashboard_router,
    files_router,
    admin_router,
):
    api_router.include_router(_module_router)
api_router.include_router(notifications_router)
