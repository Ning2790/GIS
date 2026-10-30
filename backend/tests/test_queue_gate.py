"""单机排队闸门（P1b）测试：分类、容量、503 信封、交易优先、计数释放。"""

import pytest
from fastapi.testclient import TestClient

from app.core import queue_gate
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_inflight():
    """每个用例前后清空进程内在途计数（模块级全局状态），避免互相影响。"""
    queue_gate._inflight.clear()
    yield
    queue_gate._inflight.clear()


def test_categorize_paths() -> None:
    assert queue_gate.categorize("/api/v1/shop/orders") == "trade"
    assert queue_gate.categorize("/api/v1/shop/cart/checkout") == "trade"
    assert queue_gate.categorize("/api/v1/shop/payments/1/callback") == "trade"
    # 认证类单独成档：bcrypt 慢且全程占连接，突发时要能被单独拦住
    assert queue_gate.categorize("/api/v1/auth/login") == "auth"
    assert queue_gate.categorize("/api/v1/auth/register/tourist") == "auth"
    # refresh / logout / devices 刻意落在 view 档：它们轻量，且 refresh 被打回 503
    # 会被前端当成会话失效、直接清令牌强制重登（代价远大于收益）
    assert queue_gate.categorize("/api/v1/auth/refresh") == "view"
    assert queue_gate.categorize("/api/v1/auth/logout") == "view"
    assert queue_gate.categorize("/api/v1/auth/devices") == "view"
    assert queue_gate.categorize("/api/v1/auth/password") == "auth"
    assert queue_gate.categorize("/api/v1/ai/ask") == "ai"
    assert queue_gate.categorize("/api/v1/ai/ask/stream") == "ai"
    assert queue_gate.categorize("/api/v1/travel/attractions") == "view"
    assert queue_gate.categorize("/api/v1/shop/products") == "view"
    assert queue_gate.categorize("/") == ""
    assert queue_gate.categorize("/docs") == ""


def test_view_full_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "queue_max_view", 1)
    assert queue_gate.acquire("view")  # 人为占满
    resp = client.get("/api/v1/travel/attractions", params={"page": 1, "page_size": 1})
    assert resp.status_code == 503
    assert resp.json()["code"] == 50300
    assert resp.headers["Retry-After"] == "1"
    queue_gate.release("view")
    assert (
        client.get("/api/v1/travel/attractions", params={"page": 1, "page_size": 1}).status_code
        == 200
    )


def test_trade_not_blocked_when_view_full(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """查看类满载被拒时交易类照常放行（优先保障交易）。"""
    monkeypatch.setattr(get_settings(), "queue_max_view", 1)
    assert queue_gate.acquire("view")
    resp = client.post("/api/v1/shop/orders", json={"product_id": 1, "quantity": 1})
    assert resp.status_code == 401  # 进入路由（未认证），而不是 503


def test_counter_released_after_request(client: TestClient) -> None:
    assert (
        client.get("/api/v1/travel/attractions", params={"page": 1, "page_size": 1}).status_code
        == 200
    )
    assert queue_gate._inflight["view"] == 0


def test_gate_disabled_never_blocks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "queue_enabled", False)
    assert queue_gate.capacity_of("view") == 0
    assert queue_gate.acquire("view") is True


def test_auth_gate_sheds_before_pool_starvation(client: TestClient) -> None:
    """认证档饱和 → 503；且容量配置项存在（容量与连接池对齐的口径见 docs/压测报告.md）。"""
    from app.core.config import get_settings

    settings = get_settings()
    assert settings.queue_max_auth > 0
    assert settings.queue_max_auth <= settings.queue_max_trade  # 认证最慢，容量最紧

    saturated = queue_gate.capacity_of("auth")
    try:
        queue_gate._inflight["auth"] = saturated
        resp = client.post(
            "/api/v1/auth/login", json={"phone": "13800000000", "password": "admin123456"}
        )
    finally:
        queue_gate._inflight["auth"] = 0
    assert resp.status_code == 503
    assert resp.json()["code"] == 50300
