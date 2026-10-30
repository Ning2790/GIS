"""接口限流（P1 承载能力，需求 4.3）。

固定窗口计数器（Redis INCR + EXPIRE，按窗口分桶）：实现简单、计数原子、
语义清晰，分钟粒度足以覆盖"防撞库 / 防刷单 / 防刷模型"的目标。

降级策略与项目的其他 Redis 能力一致：未配置 / 不可用时**放行**（fail-open），
限流绝不拖垮主流程；阈值 <= 0 视为关闭。接入反向代理（P3 Nginx）后，
IP 识别需改用受信代理头，当前直接使用 request.client.host。

用法（路由层，仅加依赖，不改函数签名）：

    @router.post("/login", dependencies=[Depends(rate_limit("login"))])
    @router.post("/orders", dependencies=[Depends(rate_limit("order", by="user"))])
"""

import time

from fastapi import Request

from app.api.deps import CurrentUser
from app.core import metrics
from app.core.config import get_settings
from app.core.errors import RateLimitError

WINDOW_SECONDS = 60

# scope -> Settings 字段名（阈值集中在 config.py，.env 可覆盖）
_LIMIT_SETTINGS = {
    "login": "rate_limit_login_per_minute",
    "register": "rate_limit_register_per_minute",
    "order": "rate_limit_order_per_minute",
    "ai": "rate_limit_ai_per_minute",
}

_redis_client = None


def _get_client():
    """Redis 客户端（懒加载）。未配置或不可用时返回 None（自动降级放行）。"""
    global _redis_client
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _redis_client is None:
        from redis import Redis

        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
            decode_responses=True,
        )
    return _redis_client


def _limit_of(scope: str) -> int:
    return int(getattr(get_settings(), _LIMIT_SETTINGS[scope]))


def enforce(scope: str, identity: str, limit: int) -> None:
    """执行一次计数；超限抛 RateLimitError。供依赖工厂与测试直接调用。"""
    settings = get_settings()
    if not settings.rate_limit_enabled or limit <= 0:
        return
    client = _get_client()
    if client is None:
        return  # 未配置 / 不可用：放行
    now = int(time.time())
    key = f"rl:{scope}:{identity}:{now // WINDOW_SECONDS}"
    try:
        count = client.incr(key)
        # 每次 INCR 后都续期：窗口键最多多活一个窗口，且避免"首建后崩溃"留下无 TTL 的键
        client.expire(key, WINDOW_SECONDS + 1)
    except Exception:  # Redis 故障：放行（不拖垮主流程）
        return
    if count > limit:
        metrics.record_rate_limit_hit(scope)
        retry_after = WINDOW_SECONDS - now % WINDOW_SECONDS
        raise RateLimitError(f"请求过于频繁，请 {retry_after} 秒后重试", retry_after=retry_after)


def client_ip(request: Request) -> str:
    """来源 IP：部署在受信反向代理（Nginx）后时读 X-Forwarded-For 最左地址。

    仅当 TRUST_PROXY_HEADERS=true（生产 .env 配）时启用——代理必须覆写该头；
    若服务端口直接对外暴露还开启此开关，客户端可伪造 XFF 绕过 IP 限流。
    也供其他模块记录来源信息（如设备绑定的 last_ip）。
    """
    if get_settings().trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, *, by: str = "ip"):
    """限流依赖工厂。

    by="ip"：未认证接口（登录 / 注册）按来源 IP；
    by="user"：已认证接口（下单 / AI）按用户 id，避免 NAT 后的用户互相牵连。
    """
    if scope not in _LIMIT_SETTINGS:
        raise ValueError(f"未知限流 scope：{scope}")
    if by == "user":

        def _check_user(user: CurrentUser) -> None:
            enforce(scope, f"user:{user.id}", _limit_of(scope))

        return _check_user
    if by == "ip":

        def _check_ip(request: Request) -> None:
            enforce(scope, f"ip:{client_ip(request)}", _limit_of(scope))

        return _check_ip
    raise ValueError(f"未知限流身份类型：{by}")
