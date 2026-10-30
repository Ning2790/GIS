"""单机排队闸门（P1 承载能力，需求 4.3）。

需求 4.3：超载则排队、**优先保障交易**。实现为 ASGI 层的准入计数：按类别
（交易 / AI / 普通查看）限制"在途请求数"，超限直接返回「排队中」响应
（503 + Retry-After），不让请求在进程里默默堆积到超时；交易类使用独立
配额——查看类被拒时交易照常放行。

计数是**进程内**的（本卡即"单机排队"）：无 Redis 依赖，进程崩溃计数随之
清零、不存在跨进程漂移；多实例部署时每个实例各自保护自己（总容量 = 单机
容量 × 实例数）。容量数值见 config.py，以 S6 压测结论为准。

中间件注册位置见 main.py：在 CORS 内层（CORS 在外层，保证 503 也带跨域头）。
"""

import logging
from collections import defaultdict

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import metrics
from app.core.config import get_settings
from app.core.errors import ErrorCode
from app.core.response import fail

logger = logging.getLogger(__name__)

# 豁免：探活 / 文档 / **监控端点**。闸门饱和时若把 /metrics 与看板汇总也 503，
# 恰恰在最需要观测的时刻失去观测（抓取还会白占一个名额）。
_EXEMPT_PATHS = {
    "/",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/metrics",
    "/api/v1/dashboard/metrics",
}
_EXEMPT_PREFIXES = ("/docs/", "/redoc/")
_TRADE_PREFIXES = (
    "/api/v1/shop/orders",
    "/api/v1/shop/cart/checkout",
    "/api/v1/shop/payments",
)
_AI_PREFIXES = ("/api/v1/ai/",)
# 认证类（**仅 bcrypt 重的端点**：登录 / 注册 / 改密）：bcrypt 是 CPU 密集且请求全程
# 占着数据库连接，突发（压测实测：200 用户同时注册 → 连接池被拖垮、下单连带 503）
# 必须单独设限。**刻意不含** refresh / logout / devices：它们轻量，而且 refresh 被打回
# 503 会被前端当成会话失效、直接清令牌强制重登（见 api-client 的 refreshTokens），
# 代价远大于收益——这类请求仍按 view 档放行。
_AUTH_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/password",
)

# 进程内在途计数（ASGI 事件循环单线程执行下面的同步块，无需加锁）
# 类别全集（在途/容量/看板的唯一出处）
CATEGORIES = ("view", "trade", "auth", "ai")

# 进程内在途计数（ASGI 事件循环单线程执行下面的同步块，无需加锁）
_inflight: dict[str, int] = defaultdict(int)


def categorize(path: str) -> str:
    """请求分类：trade（交易优先）/ auth（认证，最慢）/ ai / view（默认）/ ""（豁免）。"""
    if path in _EXEMPT_PATHS or path.startswith(_EXEMPT_PREFIXES):
        return ""
    if path.startswith(_AUTH_PREFIXES):
        return "auth"
    if path.startswith(_AI_PREFIXES):
        return "ai"
    if path.startswith(_TRADE_PREFIXES):
        return "trade"
    return "view"


def capacity_of(category: str) -> int:
    """类别容量；<= 0 表示不限（关闭时不拦任何请求）。"""
    settings = get_settings()
    if not settings.queue_enabled:
        return 0
    return {
        "trade": settings.queue_max_trade,
        "auth": settings.queue_max_auth,
        "ai": settings.queue_max_ai,
        "view": settings.queue_max_view,
    }.get(category, 0)


def acquire(category: str) -> bool:
    """尝试占一个在途名额（含容量判定）。"""
    limit = capacity_of(category)
    if limit <= 0:
        return True
    if _inflight[category] >= limit:
        return False
    _inflight[category] += 1
    metrics.set_queue_inflight(category, _inflight[category])
    return True


def release(category: str) -> None:
    if _inflight[category] > 0:
        _inflight[category] -= 1
        metrics.set_queue_inflight(category, _inflight[category])


def current_usage() -> dict[str, int]:
    """当前各类别在途请求数（控制台监控卡片用）。"""
    return {category: _inflight[category] for category in CATEGORIES}


class QueueGateMiddleware:
    """按类别做在途准入；超限返回 503「排队中」。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        category = categorize(scope.get("path", ""))
        if category == "" or acquire(category):
            try:
                await self.app(scope, receive, send)
            finally:
                if category:
                    release(category)
            return
        # 超限：直接给"排队中"，不让请求在进程里堆积
        metrics.record_queue_rejection(category)
        # 标记 scope：拒绝不经过路由，指标里按 queue-gate 归类（否则全落进 unmatched）
        scope[metrics.GATE_REJECTED_SCOPE_KEY] = category
        response = JSONResponse(
            status_code=503,
            content=fail(ErrorCode.UNAVAILABLE, "当前请求较多，已进入排队，请稍后重试"),
            headers={"Retry-After": "1"},
        )
        await response(scope, receive, send)
