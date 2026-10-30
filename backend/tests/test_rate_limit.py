"""限流（P1a）测试：固定窗口计数、429 信封与 Retry-After、fail-open、身份隔离。

单元测试环境无 Redis（conftest 清空 REDIS_URL）：未打桩的用例天然覆盖
fail-open 路径；需要计数的用例用 _FakeRedis 打桩。
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core import rate_limit
from app.core.config import get_settings
from app.core.errors import RateLimitError


class _FakeRedis:
    """最小 Redis 桩：只覆盖限流用到的 incr / expire。"""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(rate_limit, "_get_client", lambda: fake)
    return fake


def test_enforce_counts_and_isolates_identity(fake_redis: _FakeRedis) -> None:
    rate_limit.enforce("login", "ip:1.1.1.1", 2)
    rate_limit.enforce("login", "ip:1.1.1.1", 2)
    with pytest.raises(RateLimitError):
        rate_limit.enforce("login", "ip:1.1.1.1", 2)
    rate_limit.enforce("login", "ip:2.2.2.2", 2)  # 其他身份不受影响
    rate_limit.enforce("register", "ip:1.1.1.1", 2)  # 其他 scope 不受影响
    assert all(seconds >= rate_limit.WINDOW_SECONDS for seconds in fake_redis.expires.values())


def test_login_429_envelope_and_retry_after(
    client: TestClient, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_login_per_minute", 2)
    wrong = {"phone": "13800000000", "password": "wrong-password"}
    for _ in range(2):
        assert client.post("/api/v1/auth/login", json=wrong).status_code != 429
    resp = client.post("/api/v1/auth/login", json=wrong)
    assert resp.status_code == 429
    assert resp.json()["code"] == 42900
    assert int(resp.headers["Retry-After"]) >= 1


def test_ai_429_by_user(
    client: TestClient, fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_minute", 1)
    phone = "139" + uuid.uuid4().hex[:8]
    password = "Test123456"
    assert (
        client.post(
            "/api/v1/auth/register/tourist", json={"phone": phone, "password": password}
        ).status_code
        == 200
    )
    token = client.post("/api/v1/auth/login", json={"phone": phone, "password": password}).json()[
        "data"
    ]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert (
        client.post("/api/v1/ai/ask", json={"question": "第一次"}, headers=headers).status_code
        == 200
    )
    resp = client.post("/api/v1/ai/ask", json={"question": "第二次"}, headers=headers)
    assert resp.status_code == 429


def test_fail_open_without_redis(client: TestClient) -> None:
    """未配置 Redis（_get_client 返回 None）时限流放行，不拖垮主流程。"""
    wrong = {"phone": "13800000000", "password": "wrong-password"}
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json=wrong).status_code != 429


def test_disabled_flag(fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)
    for _ in range(5):
        rate_limit.enforce("login", "ip:1.1.1.1", 1)  # 不限流即不抛
