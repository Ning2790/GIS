"""热点缓存（P1c）测试：命中与回填、版本失效、fail-open、开关。"""

import pytest

from app.core import cache
from app.core.config import get_settings


class _FakeRedis:
    """最小 Redis 桩：只覆盖缓存用到的 get / set / incr。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex:
            self.ttls[key] = ex
        return True

    def incr(self, key: str) -> int:
        value = int(self.store.get(key, "0")) + 1
        self.store[key] = str(value)
        return value


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(cache, "_get_client", lambda: fake)
    return fake


def test_cached_hits_and_backfills(fake_redis: _FakeRedis) -> None:
    calls: list[int] = []

    def loader() -> dict:
        calls.append(1)
        return {"value": 42}

    first = cache.cached("ns", "k", 60, loader)
    second = cache.cached("ns", "k", 60, loader)
    assert first == second == {"value": 42}
    assert len(calls) == 1  # 第二次命中缓存，未再调 loader
    assert 60 in fake_redis.ttls.values()


def test_bump_invalidates(fake_redis: _FakeRedis) -> None:
    calls: list[int] = []

    def loader() -> int:
        calls.append(1)
        return len(calls)

    assert cache.cached("ns2", "k", 60, loader) == 1
    assert cache.cached("ns2", "k", 60, loader) == 1  # 命中
    cache.bump_version("ns2")
    assert cache.cached("ns2", "k", 60, loader) == 2  # 版本变化 → 未命中
    assert len(calls) == 2


def test_fail_open_without_redis() -> None:
    """未配置 Redis（单元测试环境）时每次直查：不缓存也不报错。"""
    calls: list[int] = []

    def loader() -> str:
        calls.append(1)
        return "x"

    assert cache.cached("ns3", "k", 60, loader) == "x"
    assert cache.cached("ns3", "k", 60, loader) == "x"
    assert len(calls) == 2


def test_disabled_flag(fake_redis: _FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "cache_enabled", False)
    calls: list[int] = []

    def loader() -> None:
        calls.append(1)

    cache.cached("ns4", "k", 60, loader)
    cache.cached("ns4", "k", 60, loader)
    assert len(calls) == 2
