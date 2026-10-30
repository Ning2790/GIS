"""热点读缓存（P1 承载能力，需求 4.3）。

缓存高频只读接口的**响应体**（JSON 可直接往返），适用对象：景点 / 商品
列表等"读多写少"的公开端点。

失效策略：
- TTL 兜底（cache_ttl_seconds，默认 60s）；
- 写路径调用 bump_version(namespace) 递增版本号——缓存 key 内含版本，
  旧 key 立即不再被命中（残留 key 由 TTL 自然清理，无需 SCAN 删除）。

降级：Redis 未配置 / 不可用时直接执行 loader（不缓存），与项目其他
Redis 能力一致的 fail-open 语义。

用法（见 travel / shop 路由的列表端点）：

    return cache.cached(
        "shop:products", f"{keyword or '-'}:{page.page}",
        ttl, lambda: _build_page_payload(...),
    )
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_redis_client = None


def _get_client():
    """Redis 客户端（懒加载）。未配置或不可用时返回 None（不缓存）。"""
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


def _version(namespace: str) -> int:
    client = _get_client()
    if client is None:
        return 0
    try:
        raw = client.get(f"cache:v:{namespace}")
        return int(raw) if raw is not None else 0
    except Exception:  # 读版本失败按 0 处理，不影响主流程
        return 0


def bump_version(namespace: str) -> None:
    """写路径调用：该命名空间的全部缓存立即失效（旧 key 由 TTL 清理）。"""
    client = _get_client()
    if client is None:
        return
    try:
        client.incr(f"cache:v:{namespace}")
    except Exception:
        pass


def cached[T](namespace: str, key_parts: str, ttl: int, loader: Callable[[], T]) -> T:
    """读缓存；未命中执行 loader 并回填。Redis 不可用 / 关闭时直接 loader。"""
    settings = get_settings()
    client = _get_client()
    if not settings.cache_enabled or ttl <= 0 or client is None:
        return loader()

    key = f"cache:{namespace}:{_version(namespace)}:{key_parts}"
    try:
        raw: Any = client.get(key)
        if raw is not None:
            return json.loads(raw)
    except Exception:  # 反序列化或读失败：回退直查
        return loader()

    value = loader()
    try:
        client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception:  # 写缓存失败不影响本次响应
        pass
    return value
