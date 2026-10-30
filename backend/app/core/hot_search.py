"""搜索热词统计（增强项，需求 2.3 搜索推荐）。

Redis 有序集合累计关键词的搜索次数（``ZINCRBY``），整键 7 天过期兜底
（**近似窗口**：任意一次搜索都会刷新整键 TTL，分数不单独衰减——热词是"最近
一周的近似热度"，不追求精确的时间窗）。
未配置 / 不可用时**全部静默降级**（记录不做、读取返回空），与项目其它 Redis
能力一致的 fail-open 语义——热词只是"锦上添花"，绝不能影响搜索本身。

为什么必须限制规模：记录发生在**公开无鉴权的搜索接口**上，每个新关键词都会
新建一个集合成员，而 Redis 是多个能力（限流计数、库存预扣闸门、读缓存）共用的
实例——没有上限的话，匿名流量可以把集合撑到撑爆实例，连交易链路一起拖挂。
因此收录前做字符集过滤（必须含字母 / 数字 / 汉字，挡掉控制字符与零宽字符），
并按调用次数定期 `ZREMRANGEBYRANK` 只保留热度前 MAX_MEMBERS 个。

为什么不落库：热词是近似统计（允许丢失、允许近似），落库会给每一次搜索
带来一次写放大。
"""

import logging
import re
import time

from app.core.config import get_settings

logger = logging.getLogger(__name__)

#: 有序集合键：score = 窗口内的搜索次数
KEY = "shop:hot_search"
#: 整键过期（每次记录刷新）：7 天
TTL_SECONDS = 7 * 24 * 3600
#: 收录的关键词长度区间（1 个字太泛、过长的多半是误输入）
MIN_KEYWORD_LENGTH = 2
MAX_KEYWORD_LENGTH = 24
#: 集合成员上限：超出后按分数裁掉尾部（防匿名流量把共享 Redis 撑爆）
MAX_MEMBERS = 500
#: 每 N 次记录做一次裁剪（每次都裁太贵）
TRIM_EVERY = 50
#: 连续失败后的熔断时长（秒）：Redis 挂了不能让每次搜索都等超时
FAIL_COOLDOWN_SECONDS = 30

_write_count = 0
_fail_until = 0.0

_redis_client = None


def _get_client():
    """Redis 客户端（懒加载）。未配置、熔断中或不可用时返回 None（降级）。"""
    global _redis_client
    if time.monotonic() < _fail_until:  # 熔断：已知 Redis 不通就不再逐次等超时
        return None
    settings = get_settings()
    if not settings.redis_url:
        return None
    if _redis_client is None:
        from redis import Redis

        _redis_client = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
            decode_responses=True,
        )
    return _redis_client


def _trip(scope: str) -> None:
    """记录一次失败并进入熔断窗口（热词不可用只是少统计，绝不能拖慢搜索）。"""
    global _fail_until
    _fail_until = time.monotonic() + FAIL_COOLDOWN_SECONDS
    logger.debug("热词 %s 失败，熔断 %s 秒", scope, FAIL_COOLDOWN_SECONDS)


#: 至少含一个字母 / 数字 / 汉字：挡掉纯控制字符、零宽字符、纯标点与 emoji
_MEANINGFUL = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")


def normalize(keyword: str | None) -> str | None:
    """规整关键词：去首尾空白；太短 / 太长 / 无实义字符返回 None（不收录）。"""
    if keyword is None:
        return None
    cleaned = "".join(char for char in keyword.strip() if char.isprintable())
    if not MIN_KEYWORD_LENGTH <= len(cleaned) <= MAX_KEYWORD_LENGTH:
        return None
    if not _MEANINGFUL.search(cleaned):
        return None
    return cleaned


def record(keyword: str | None) -> None:
    """记一次搜索（关键词为空 / 不符合要求则跳过；Redis 异常静默并熔断）。

    计的是"列表请求次数"：翻页与命中缓存都会再计一次（近似统计，见 docs/部署.md）。
    """
    global _write_count
    cleaned = normalize(keyword)
    if cleaned is None:
        return
    client = _get_client()
    if client is None:
        return
    try:
        # pipeline：ZINCRBY + EXPIRE + （每 N 次）裁剪一起发，减少往返
        pipe = client.pipeline()
        pipe.zincrby(KEY, 1, cleaned)
        pipe.expire(KEY, TTL_SECONDS)
        _write_count += 1
        if _write_count % TRIM_EVERY == 0:
            pipe.zremrangebyrank(KEY, 0, -(MAX_MEMBERS + 1))  # 只留热度前 MAX_MEMBERS
        pipe.execute()
    except Exception:  # noqa: BLE001 - 热词统计失败不能影响搜索
        _trip(f"write:{cleaned[:16]}")


def top(limit: int = 10) -> list[tuple[str, int]]:
    """热度前 N 的关键词（按次数降序，同分按字典序）；Redis 不可用时返回空表。"""
    client = _get_client()
    if client is None:
        return []
    try:
        rows = client.zrevrange(KEY, 0, max(0, limit - 1), withscores=True)
    except Exception:  # noqa: BLE001 - 读失败按"暂无热词"处理
        _trip("read")
        return []
    return [(str(keyword), int(score)) for keyword, score in rows]
