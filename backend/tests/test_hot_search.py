"""搜索热词（增强项）测试：Redis 累计与降级。

单测环境未配置 Redis（conftest 清空 REDIS_URL）→ 天然覆盖降级路径；
累计与读取用假客户端打桩。
"""

from fastapi.testclient import TestClient

from app.core import hot_search
from app.core.config import get_settings


class _Pipe:
    """pipeline 桩：把命令排起来一次执行（与 redis-py 的用法一致）。"""

    def __init__(self, client):  # noqa: ANN001
        self.client = client
        self.commands: list[tuple[str, tuple]] = []

    def zincrby(self, key: str, amount: float, member: str):
        self.commands.append(("zincrby", (key, amount, member)))
        return self

    def expire(self, key: str, seconds: int):
        self.commands.append(("expire", (key, seconds)))
        return self

    def zremrangebyrank(self, key: str, start: int, end: int):
        self.commands.append(("zremrangebyrank", (key, start, end)))
        return self

    def execute(self):
        return [getattr(self.client, name)(*args) for name, args in self.commands]


class FakeRedis:
    """最小有序集合桩：只实现热词用到的命令。"""

    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, float]] = {}
        self.expires: dict[str, int] = {}
        self.pipeline_count = 0

    def pipeline(self):
        self.pipeline_count += 1
        return _Pipe(self)

    def zincrby(self, key: str, amount: float, member: str) -> float:
        bucket = self.zsets.setdefault(key, {})
        bucket[member] = bucket.get(member, 0) + amount
        return bucket[member]

    def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True

    def zremrangebyrank(self, key: str, start: int, end: int) -> int:
        """按分数升序裁掉排名区间（与 Redis 一致：负索引从尾部数、越界夹紧）。"""
        bucket = self.zsets.get(key, {})
        ordered = sorted(bucket.items(), key=lambda item: (item[1], item[0]))
        size = len(ordered)
        begin = size + start if start < 0 else start
        finish = size + end if end < 0 else end
        begin = max(begin, 0)
        finish = min(finish, size - 1)
        removed = ordered[begin : finish + 1] if begin <= finish else []
        for name, _score in removed:
            bucket.pop(name, None)
        return len(removed)

    def zrevrange(self, key: str, start: int, end: int, withscores: bool = False):
        rows = sorted(self.zsets.get(key, {}).items(), key=lambda item: (-item[1], item[0]))
        return rows[start : end + 1]


def test_normalize_rules() -> None:
    assert hot_search.normalize("  牦牛肉干  ") == "牦牛肉干"
    assert hot_search.normalize("茶") is None  # 单字太泛
    assert hot_search.normalize("") is None
    assert hot_search.normalize(None) is None
    assert hot_search.normalize("长" * 25) is None  # 超长（多半是误输入）


def test_normalize_rejects_meaningless_characters() -> None:
    """无实义字符不收录（复审发现：控制字符 / 零宽字符会让热词榜出现空胶囊）。"""
    assert hot_search.normalize("a" + chr(0) + "b") == "ab"  # 不可打印字符被剔除后仍是有效词
    assert hot_search.normalize("​​") is None  # 纯零宽空格
    assert hot_search.normalize("！？") is None  # 纯标点
    assert hot_search.normalize("🔥🔥") is None  # 纯 emoji
    assert hot_search.normalize(chr(27) + chr(27)) is None  # 纯控制字符
    assert hot_search.normalize(chr(27) + "[31m") == "[31m"  # 控制字符被剔除，可见部分保留
    assert hot_search.normalize("A1") == "A1"  # 字母数字有效


def test_record_and_top_with_fake_redis(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(hot_search, "_get_client", lambda: fake)

    for keyword in ("牦牛肉干", "雪菊", "牦牛肉干", "牦牛肉干", "雪菊", "菜籽油"):
        hot_search.record(keyword)
    hot_search.record("茶")  # 单字不收录
    hot_search.record(None)  # 空关键词不收录

    assert hot_search.top(2) == [("牦牛肉干", 3), ("雪菊", 2)]
    assert all(count == hot_search.TTL_SECONDS for count in fake.expires.values())  # 滑动窗口 TTL
    assert "茶" not in fake.zsets[hot_search.KEY]


def test_record_swallows_redis_errors(monkeypatch) -> None:
    class Boom(FakeRedis):
        def zincrby(self, *args, **kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr(hot_search, "_get_client", lambda: Boom())
    hot_search.record("牦牛肉干")  # 不应抛出（热词统计失败不能影响搜索）


def test_degraded_without_redis() -> None:
    """未配置 Redis：记录是空操作、读取返回空表（搜索本身不受影响）。"""
    assert hot_search._get_client() is None
    hot_search.record("牦牛肉干")
    assert hot_search.top(10) == []


def test_hot_keywords_endpoint_degrades_to_empty(client: TestClient) -> None:
    assert client.get("/api/v1/shop/hot-keywords").json()["data"]["items"] == []


def test_hot_keywords_endpoint_with_fake_redis(client: TestClient, monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(hot_search, "_get_client", lambda: fake)

    client.get("/api/v1/shop/products?keyword=牦牛肉干&page=1")
    client.get("/api/v1/shop/products?keyword=牦牛肉干&page=1")
    client.get("/api/v1/shop/products?keyword=雪菊&page=1")
    # 命中缓存也要记（记录在缓存之外）；无关键词的列表不计入
    client.get("/api/v1/shop/products?page=1")

    resp = client.get("/api/v1/shop/hot-keywords?limit=5")
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == [
        {"keyword": "牦牛肉干", "count": 2},
        {"keyword": "雪菊", "count": 1},
    ]


def test_hot_keywords_limit_is_validated(client: TestClient) -> None:
    assert client.get("/api/v1/shop/hot-keywords?limit=0").status_code == 422
    assert client.get("/api/v1/shop/hot-keywords?limit=99").status_code == 422


def test_members_are_trimmed_to_cap(monkeypatch) -> None:
    """成员上限：超过 MAX_MEMBERS 的尾部会被裁掉（防公开接口撑爆共享 Redis）。"""
    fake = FakeRedis()
    monkeypatch.setattr(hot_search, "_get_client", lambda: fake)
    monkeypatch.setattr(hot_search, "MAX_MEMBERS", 5)
    monkeypatch.setattr(hot_search, "TRIM_EVERY", 1)  # 每次记录都裁，便于断言

    for index in range(8):
        hot_search.record(f"关键词{index}")  # 每个词 1 分，同分按字典序
    assert len(fake.zsets[hot_search.KEY]) == 5
    assert "关键词0" not in fake.zsets[hot_search.KEY]  # 尾部（分数最低）被裁


def test_failures_trip_circuit_breaker(monkeypatch) -> None:
    """Redis 故障后进入熔断：窗口内的调用不再尝试连 Redis（列表是高频路径）。"""
    monkeypatch.setattr(hot_search, "_redis_client", None)
    monkeypatch.setattr(hot_search, "_fail_until", 0.0)
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:6399/0")  # 不可达端口

    reads = {"count": 0}

    class Boom(FakeRedis):
        def pipeline(self):
            reads["count"] += 1
            raise RuntimeError("redis down")

    monkeypatch.setattr(hot_search, "_redis_client", Boom())
    hot_search.record("牦牛肉干")
    assert hot_search._fail_until > 0  # 已熔断
    assert reads["count"] == 1

    hot_search.record("雪菊")  # 熔断窗口内：连 pipeline 都不再触发
    assert reads["count"] == 1
    assert hot_search.top(5) == []  # 读路径同样短路
