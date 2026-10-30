"""运行指标（N10）：Prometheus 文本端点 + 控制台概览的 JSON 汇总。"""

import re

from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.core import metrics, queue_gate
from app.db.session import SessionLocal
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus


def _admin_headers(client: TestClient) -> dict[str, str]:
    """创建（幂等）并登录测试管理员，返回请求头。"""
    from app.core.errors import ConflictError

    with SessionLocal() as db:
        try:
            users_service.create_admin(db, phone="13700000000", password="admin123456")
        except ConflictError:
            pass
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13700000000", "password": "admin123456"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _merchant_headers(client: TestClient) -> dict[str, str]:
    import uuid

    from app.core.security import hash_password
    from app.modules.users.models import UserRole

    phone = "13" + str(uuid.uuid4().int)[:9]
    with SessionLocal() as db:
        db.add(
            User(
                phone=phone,
                password_hash=hash_password("secret123"),
                role=UserRole.MERCHANT,
                status=UserStatus.ACTIVE,
                nickname="指标测试商户",
            )
        )
        db.commit()
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": "secret123"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def _metric_value(name: str) -> float:
    """从注册表读某条指标的当前值（无标签或任意标签求和）。"""
    total = 0.0
    for metric in getattr(metrics, name).collect():
        for sample in metric.samples:
            if sample.name == name:
                total += sample.value
    return total


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    """`/metrics` 输出 Prometheus 文本（不经统一响应信封），含核心指标名。"""
    client.get("/api/v1/shop/products")  # 先产生一次观测，直方图才会有样本
    resp = client.get("/metrics")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "http_requests_total" in body
    assert "http_request_duration_seconds_bucket" in body
    assert "queue_rejections_total" in body
    assert "stock_gate_drift_total" in body
    # 不经信封：响应体不是 {code,msg,data}
    assert body.lstrip().startswith("# HELP") or body.lstrip().startswith("# TYPE")


def test_metrics_scrape_itself_is_not_counted(client: TestClient) -> None:
    """抓取 /metrics 自身不计入指标，避免监控流量污染业务口径。"""
    before = _metric_value("http_requests_total")
    client.get("/metrics")
    client.get("/metrics")
    assert _metric_value("http_requests_total") == before


def test_requests_counted_by_route_template(client: TestClient) -> None:
    """接口请求计入指标，且路径标签是**路由模板**（不含具体 id）。"""
    client.get("/api/v1/shop/products")
    body = client.get("/metrics").text
    assert 'path="/api/v1/shop/products"' in body

    # 路径参数用模板占位：具体 id 不进标签（否则标签基数随业务数据无限增长）
    client.get("/api/v1/shop/products/123456")
    body = client.get("/metrics").text
    assert re.search(r'path="/api/v1/shop/products/\{[a-z_]+\}"', body), body
    assert 'path="/api/v1/shop/products/123456"' not in body


def test_unmatched_paths_collapse_to_one_label(client: TestClient) -> None:
    """未匹配路径（扫描 / 拼错）统一记 `unmatched`，不给每个随机路径开一条时间序列。"""
    client.get("/api/v1/zzz-attacker-unique-1")
    client.get("/api/v1/zzz-attacker-unique-2")
    body = client.get("/metrics").text
    assert 'path="unmatched"' in body
    assert "zzz-attacker-unique-1" not in body
    assert "zzz-attacker-unique-2" not in body


def test_queue_rejection_is_counted_and_monitoring_stays_readable(client: TestClient) -> None:
    """闸门拒绝要计数；闸门饱和时 `/metrics` 仍可读（过载时不能失去观测）。"""
    before = _metric_value("queue_rejections_total")
    saturated = queue_gate.capacity_of("view")
    assert saturated > 0, "测试环境需启用排队闸门"
    try:
        queue_gate._inflight["view"] = saturated  # 占满 view 配额，模拟过载
        assert client.get("/api/v1/shop/products").status_code == 503
        body = client.get("/metrics").text
        # 拒绝的请求没进路由：按 queue-gate 归类，而不是混进 unmatched
        assert 'path="queue-gate",status="503"' in body
        assert client.get("/metrics").status_code == 200
        assert queue_gate.categorize("/metrics") == ""  # 抓取不占名额
    finally:
        queue_gate._inflight["view"] = 0
    assert _metric_value("queue_rejections_total") == before + 1


def test_stock_gate_drift_is_counted() -> None:
    """库存闸门写回时发现与 Redis 现值不一致（含值损坏）会记一次回补。"""

    class _FakeRedis:
        def __init__(self, value: str | None) -> None:
            self.value = value
            self.written: list[tuple[str, int]] = []

        def get(self, key: str) -> str | None:  # noqa: ARG002 - 桩只需返回现值
            return self.value

        def set(self, key: str, value: int, ex: int | None = None) -> None:  # noqa: ARG002
            self.written.append((key, value))

    from app.modules.shop import service as shop_service

    original = shop_service._get_redis
    try:
        for redis_value, expected in (("5", 1), ("not-a-number", 1), ("10", 0)):
            fake = _FakeRedis(redis_value)
            shop_service._get_redis = lambda fake=fake: fake  # type: ignore[assignment]
            before = _metric_value("stock_gate_drift_total")
            shop_service._redis_sync(1, 10)
            assert _metric_value("stock_gate_drift_total") == before + expected, redis_value
            assert fake.written == [("shop:stock:1", 10)], redis_value  # 一律写回权威值
    finally:
        shop_service._get_redis = original  # type: ignore[assignment]


def test_dashboard_metrics_requires_admin(client: TestClient) -> None:
    """指标汇总是平台级数据：仅管理员可读。"""
    assert client.get("/api/v1/dashboard/metrics").status_code == 401
    assert (
        client.get("/api/v1/dashboard/metrics", headers=_merchant_headers(client)).status_code
        == 403
    )


def test_dashboard_metrics_shape(client: TestClient) -> None:
    """管理员可读，字段齐备且与 /metrics 同源（含队列在途与容量）。"""
    client.get("/api/v1/shop/products")  # 制造一次请求，保证 P95 有数据
    resp = client.get("/api/v1/dashboard/metrics", headers=_admin_headers(client))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    for key in (
        "requests_total",
        "server_error_total",
        "latency_p95_seconds",
        "latency_avg_seconds",
        "rate_limit_hits_total",
        "queue_rejections_total",
        "stock_gate_drift_total",
        "queue_inflight",
        "queue_capacity",
    ):
        assert key in data, key
    assert data["requests_total"] >= 1
    assert set(data["queue_inflight"]) == {"view", "trade", "auth", "ai"}
    assert data["queue_capacity"]["trade"] >= 0


def test_counters_feed_snapshot(client: TestClient) -> None:
    """排队拒绝 / 限流命中的计数会进入汇总（拒绝路径本身用 Redis，单测里直接计数验证接线）。"""
    before = metrics.snapshot()["queue_rejections_total"]
    metrics.record_queue_rejection("view")
    metrics.record_rate_limit_hit("order")
    after = metrics.snapshot()
    assert after["queue_rejections_total"] == before + 1
    assert after["rate_limit_hits_total"] >= 1


def test_queue_inflight_gauge_tracks_gate() -> None:
    """在途数要有 Prometheus gauge（控制台读 JSON 快照，Prometheus 侧读 gauge）。"""
    before = queue_gate.current_usage()["ai"]
    assert queue_gate.acquire("ai") is True
    try:
        assert queue_gate.current_usage()["ai"] == before + 1
        body = generate_latest().decode()
        assert 'queue_inflight{category="ai"}' in body
        import re

        value = float(re.search(r'queue_inflight\{category="ai"\} (\S+)', body).group(1))
        assert value == before + 1
    finally:
        queue_gate.release("ai")
    assert queue_gate.current_usage()["ai"] == before


def test_queue_gate_usage_shape() -> None:
    """闸门在途用量按三档返回（监控卡片展示用）。"""
    usage = queue_gate.current_usage()
    assert set(usage) == {"view", "trade", "auth", "ai"}
    assert all(isinstance(value, int) for value in usage.values())
