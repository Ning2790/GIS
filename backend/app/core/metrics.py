"""指标（N10）：Prometheus 文本端点 + 控制台概览用的 JSON 汇总。

**只汇总 API 进程**（Celery worker 是独立进程，任务成败先靠日志与审计）。

**多实例部署**：注册表是进程内的，每个实例只统计自己处理的请求；看板卡片显示的是
「应答实例」的口径，Prometheus 应逐实例抓取（多 target / file_sd）。

指标与埋点位置：
- `http_requests_total` / `http_request_duration_seconds`：HTTP 中间件按**路由模板**统计
  （用模板而非原始 URL，避免路径参数与 404 扫描把标签基数打爆）
- `rate_limit_hits_total{scope}`：限流命中（`core/rate_limit.py`）
- `queue_rejections_total{category}`：排队闸门拒绝（`core/queue_gate.py`）
- `queue_inflight{category}`：闸门在途请求数（gauge；闸门准入 / 释放时更新）
- `stock_gate_drift_total`：库存闸门与数据库不一致而补偿的次数（`shop/service.py`）
- `db_pool_timeout_total`：连接池等连接超时（**过载**；`main.py` 统一回 503 + Retry-After）
- `db_unavailable_total`：数据库不可达 / 连接中断（**依赖故障**；同样回 503，但告警口径不同）
- `db_statement_timeout_total`：慢查询被语句超时掐断（SQLSTATE 57014；回 503 但**不是**库故障，
  看到它涨应该去优化慢查询，而不是查数据库可用性）
- `db_unretryable_failure_total`：已提交后失败 / 提交结果未知（回 500 且**不带** Retry-After，
  不许客户端重试——否则重复下单；这是最需要人工关注的信号）

`/metrics` 输出 Prometheus 文本（不经统一响应信封），部署时由网关限制为**内网可读**；
控制台概览的监控卡片读 `snapshot()`（同一份注册表的 JSON 汇总），无需抓取文本。
"""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.types import Scope

from app.core.config import get_settings

# 闸门拒绝请求的 scope 标记（由 queue_gate 写入，metrics 读作路径标签）
GATE_REJECTED_SCOPE_KEY = "qh_queue_gate_rejected"


def path_label(scope: Scope) -> str:
    """路径标签：取 Starlette 写入的**路由模板**（`scope["route"]`），未匹配的记为 `unmatched`。

    用模板而不是原始 URL：路径参数（订单号 / 商品 id）与 404 扫描路径若进标签，
    每个新取值都会永久新增一组时间序列（标签基数爆炸），且无法按接口聚合。
    未匹配路径（扫描 / 拼错）统一成单个 `unmatched` 序列，数量本身即 404 信号。

    被排队闸门挡下的请求**还没进路由**（闸门在路由外层直接回 503），按类别记成
    单个 `queue-gate` 序列——具体是哪个接口被拒看 `queue_rejections_total{category}`，
    那里有闸门分类（view / trade / auth / ai），比拿未匹配的原始路径猜测更准。
    """
    if scope.get(GATE_REJECTED_SCOPE_KEY):
        return "queue-gate"
    template = getattr(scope.get("route"), "path", None)
    if not template:
        return "unmatched"
    prefix = get_settings().api_v1_prefix
    raw_path = scope.get("path", "")
    # 本 FastAPI 版本下模板不含 include_router 的前缀，补回来才与真实 URL 一致；
    # 直接注册在 app 上的路由（/、/metrics）模板已含完整路径，不能重复拼。
    if raw_path.startswith(prefix) and not template.startswith(prefix):
        return prefix + template
    return template


http_requests_total = Counter(
    "http_requests_total",
    "HTTP 请求数（按方法 / 路由模板 / 状态码）",
    ["method", "path", "status"],
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP 请求耗时（秒，按方法 / 路由模板）",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
rate_limit_hits_total = Counter("rate_limit_hits_total", "限流命中次数（按限流范围）", ["scope"])
queue_rejections_total = Counter(
    "queue_rejections_total", "排队闸门拒绝次数（按类别）", ["category"]
)
stock_gate_drift_total = Counter("stock_gate_drift_total", "库存闸门与数据库不一致后的补偿次数")
db_pool_timeout_total = Counter(
    "db_pool_timeout_total", "数据库连接池等连接超时次数（过载信号，见 main.py 的 503 映射）"
)
db_unavailable_total = Counter(
    "db_unavailable_total",
    "数据库不可达 / 连接中断次数（依赖故障信号；与池超时区分，见 main.py）",
)
retention_deleted_total = Counter(
    "retention_deleted_total", "保留期清理删除条数（按表）", ["table"]
)
queue_inflight = Gauge(
    "queue_inflight",
    "排队闸门在途请求数（按类别；控制台卡片读同一份数据）",
    ["category"],
)
db_unretryable_failure_total = Counter(
    "db_unretryable_failure_total",
    "数据库失败且**不可安全重试**的次数（已提交后失败 / 提交结果未知；见 main.py）",
)
db_statement_timeout_total = Counter(
    "db_statement_timeout_total",
    "慢查询被 statement_timeout 掐断的次数（SQLSTATE 57014；与「库不可用」区分，便于分诊）",
)


def observe_request(*, method: str, path: str, status: int, duration_seconds: float) -> None:
    """记录一次 HTTP 请求（由 main.py 的中间件调用）。"""
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration_seconds)


def record_rate_limit_hit(scope: str) -> None:
    rate_limit_hits_total.labels(scope=scope).inc()


def set_queue_inflight(category: str, value: int) -> None:
    """更新某类别的在途数（由 queue_gate 的准入/释放调用）。"""
    queue_inflight.labels(category=category).set(value)


def record_queue_rejection(category: str) -> None:
    queue_rejections_total.labels(category=category).inc()


def record_stock_gate_drift() -> None:
    stock_gate_drift_total.inc()


def render_latest() -> bytes:
    """Prometheus 文本输出（供 /metrics 端点）。"""
    return generate_latest()


def prometheus_content_type() -> str:
    return CONTENT_TYPE_LATEST


def _sum_by_le() -> tuple[dict[float, float], float, float]:
    """把耗时直方图跨方法 / 路由聚合：返回 (按桶上界的累计计数, 总次数, 总耗时秒)。"""
    buckets: dict[float, float] = {}
    count = 0.0
    total_seconds = 0.0
    for metric in http_request_duration_seconds.collect():
        for sample in metric.samples:
            if sample.name == "http_request_duration_seconds_bucket":
                upper = float(sample.labels["le"])
                buckets[upper] = buckets.get(upper, 0.0) + sample.value
            elif sample.name == "http_request_duration_seconds_count":
                count += sample.value
            elif sample.name == "http_request_duration_seconds_sum":
                total_seconds += sample.value
    return buckets, count, total_seconds


def _quantile(buckets: dict[float, float], count: float, quantile: float) -> float | None:
    """按 Prometheus 的经典做法从桶估算分位（桶内线性插值），够看趋势。"""
    if count <= 0 or not buckets:
        return None
    target = quantile * count
    previous_upper = 0.0
    previous_count = 0.0
    for upper in sorted(buckets):
        cumulative = buckets[upper]
        if cumulative >= target:
            if upper == float("inf"):
                return previous_upper
            bucket_count = cumulative - previous_count
            if bucket_count <= 0:
                return upper
            ratio = (target - previous_count) / bucket_count
            return previous_upper + (upper - previous_upper) * ratio
        previous_upper, previous_count = upper, cumulative
    return None


def snapshot() -> dict:
    """概览监控卡片的 JSON 汇总（与 /metrics 同源，避免两套口径）。"""
    from app.core import queue_gate

    requests_total = 0.0
    server_errors = 0.0
    for metric in http_requests_total.collect():
        for sample in metric.samples:
            if sample.name != "http_requests_total":
                continue
            requests_total += sample.value
            if sample.labels.get("status", "").startswith("5"):
                server_errors += sample.value

    buckets, count, total_seconds = _sum_by_le()
    drift = 0.0
    for metric in stock_gate_drift_total.collect():
        for sample in metric.samples:
            if sample.name == "stock_gate_drift_total":
                drift += sample.value
    rate_limited = 0.0
    for metric in rate_limit_hits_total.collect():
        for sample in metric.samples:
            if sample.name == "rate_limit_hits_total":
                rate_limited += sample.value
    rejected = 0.0
    for metric in queue_rejections_total.collect():
        for sample in metric.samples:
            if sample.name == "queue_rejections_total":
                rejected += sample.value

    def _counter_total(counter: object) -> float:
        total = 0.0
        for metric in counter.collect():  # type: ignore[attr-defined]
            for sample in metric.samples:
                if sample.name == getattr(counter, "_name", ""):
                    total += sample.value
        return total

    db_unavailable = _counter_total(db_unavailable_total)
    db_unretryable = _counter_total(db_unretryable_failure_total)

    p95 = _quantile(buckets, count, 0.95)
    return {
        "requests_total": int(requests_total),
        "server_error_total": int(server_errors),
        "latency_p95_seconds": round(p95, 4) if p95 is not None else None,
        "latency_avg_seconds": round(total_seconds / count, 4) if count else None,
        "rate_limit_hits_total": int(rate_limited),
        "queue_rejections_total": int(rejected),
        "stock_gate_drift_total": int(drift),
        "db_unavailable_total": int(db_unavailable),
        "db_unretryable_failure_total": int(db_unretryable),
        "queue_inflight": queue_gate.current_usage(),
        "queue_capacity": {
            category: queue_gate.capacity_of(category) for category in queue_gate.CATEGORIES
        },
    }


class MetricsMiddleware:
    """按**路由模板**统计请求数与耗时的 ASGI 中间件（N10）。

    - 路径标签取 `path_label()`：库写入的路由模板（`/api/v1/shop/orders/{order_id}`），
      未匹配路径记 `unmatched`，避免路径参数与扫描流量打爆标签基数；
    - 自身 `/metrics` 的抓取不计入（否则监控流量会污染业务指标）；
    - 放在排队闸门**外层**（见 main.py 的 add 顺序），闸门拒绝的 503 也计入。
    """

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI 应用
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500

        async def send_wrapper(message) -> None:  # noqa: ANN001
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            observe_request(
                method=scope.get("method", ""),
                path=path_label(scope),
                status=status,
                duration_seconds=time.perf_counter() - started,
            )
