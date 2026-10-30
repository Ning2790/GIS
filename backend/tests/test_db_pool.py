"""数据库连接池与依赖故障的语义测试。

两类失败要分开，且**能不能让客户端重试**必须由「本次请求是否已提交」决定：

- 提交前失败（过载 / 依赖故障）→ 503 + Retry-After（重试安全）；
- **提交后失败**（写已落库）或提交结果未知（SQLSTATE 40003）→ 500 且**不带** Retry-After，
  否则客户端重试会造成重复写入（下单 / 售后 / 发消息等接口的幂等键是可选的）。
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DisconnectionError as DBDisconnectionError
from sqlalchemy.exc import OperationalError as DBOperationalError
from sqlalchemy.exc import TimeoutError as DBTimeoutError
from sqlalchemy.pool import QueuePool

from app.api.deps import DbSession
from app.core.config import get_settings
from app.db.session import connect_args_for, engine


def _counter(body: str, name: str) -> float:
    match = re.search(rf"^{name} (\S+)$", body, re.M)
    return float(match.group(1)) if match else 0.0


def _counters(client: TestClient) -> dict[str, float]:
    body = client.get("/metrics").text
    return {
        name: _counter(body, name)
        for name in (
            "db_pool_timeout_total",
            "db_unavailable_total",
            "db_unretryable_failure_total",
            "db_statement_timeout_total",
        )
    }


def _pool_connect_params(target_engine: object) -> dict[str, object]:
    """从引擎的池创建函数闭包里取出生效的连接参数（SQLAlchemy 不公开该信息）。

    只用于测试：证明 `connect_args_for()` 的结果真的传进了 `create_engine`，
    而不是「定义了却没接线」。
    """
    creator = getattr(getattr(target_engine, "pool", None), "_creator", None)
    for cell in getattr(creator, "__closure__", None) or ():
        value = cell.cell_contents
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if k != "context"}
    pytest.skip("当前 SQLAlchemy 版本的池创建函数结构不同，跳过接线断言")


def test_engine_pool_matches_settings() -> None:
    if not isinstance(engine.pool, QueuePool):
        pytest.skip("当前方言未使用 QueuePool（如 SQLite 内存库），跳过")
    settings = get_settings()
    assert engine.pool.size() == settings.db_pool_size
    assert engine.pool._max_overflow == settings.db_max_overflow


def test_connect_args_are_dialect_aware() -> None:
    """连接参数按方言给：PG 必须带 connect_timeout（否则不可达时会挂到分钟级）。"""
    pg = connect_args_for("postgresql+psycopg://u:p@127.0.0.1:5432/db", 7)
    assert pg == {"connect_timeout": 7}
    # 语句超时经 options 传给会话；0 表示不设（不污染 connect_args）
    with_statement = connect_args_for("postgresql+psycopg://u:p@h/db", 7, 10_000)
    assert with_statement["options"] == "-c statement_timeout=10000"
    assert "options" not in pg
    # 连接超时必须小于连接池等待时间，且不为 0（libpq 语义：0 = 不超时）
    assert connect_args_for("postgresql+psycopg://u:p@h/db", 0)["connect_timeout"] == 1

    sqlite = connect_args_for("sqlite:///./dev.db", 7)
    assert sqlite == {"check_same_thread": False}
    assert "connect_timeout" not in sqlite

    assert connect_args_for("mysql+pymysql://u:p@h/db", 7) == {}


def test_engine_actually_uses_connect_args() -> None:
    """engine 真的用上了 connect_args_for 的结果（变异测试防线：接线断开即失败）。"""
    params = _pool_connect_params(engine)
    if engine.dialect.name == "sqlite":
        assert params.get("check_same_thread") is False
    else:
        assert "connect_timeout" in params


def test_connect_timeout_below_pool_timeout() -> None:
    """默认值要保证「连不上」先暴露：否则请求先耗尽池、被误记成过载。"""
    settings = get_settings()
    assert 0 < settings.db_connect_timeout < settings.db_pool_timeout


def test_pool_timeout_maps_to_503(client: TestClient) -> None:
    """等连接超时按**过载**返回 503 + Retry-After（而不是 500）。"""
    from app.api.deps import get_db

    def _exhausted() -> None:
        raise DBTimeoutError("QueuePool limit of size 20 overflow 20 reached")

    app = client.app  # type: ignore[attr-defined]
    before = _counters(client)
    app.dependency_overrides[get_db] = _exhausted
    try:
        resp = client.get("/api/v1/shop/products")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == 50300
    assert resp.headers["retry-after"] == "1"
    after = _counters(client)
    assert after["db_pool_timeout_total"] == before["db_pool_timeout_total"] + 1
    assert after["db_unavailable_total"] == before["db_unavailable_total"]
    assert after["db_unretryable_failure_total"] == before["db_unretryable_failure_total"]


def test_post_commit_gate_sync_never_fails_the_request() -> None:
    """提交后的闸门对账（_sync_all）遇池超时只记日志——订单已成交，不能返回失败。"""
    from app.modules.shop import service as shop_service

    class _BrokenSession:
        def refresh(self, _obj: object) -> None:
            raise DBTimeoutError("QueuePool limit reached")

        def rollback(self) -> None:
            self.rolled_back = True

    session = _BrokenSession()
    product = type("P", (), {"id": 1, "stock": 5})()
    shop_service._sync_all(session, {1: product})  # 不抛即通过
    assert session.rolled_back is True


@pytest.mark.parametrize(
    "exc",
    [
        DBOperationalError("SELECT 1", {}, Exception("could not connect to server")),
        DBDisconnectionError("server closed the connection unexpectedly"),
    ],
    ids=["operational_error", "disconnection_error"],
)
def test_db_unavailable_maps_to_503(client: TestClient, exc: Exception) -> None:
    """**提交前**的数据库不可达 / 连接中断 → 503 + Retry-After（重试安全）。"""
    from app.api.deps import get_db

    def _dead() -> None:
        raise exc

    app = client.app  # type: ignore[attr-defined]
    before = _counters(client)
    app.dependency_overrides[get_db] = _dead
    try:
        resp = client.get("/api/v1/shop/products")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == 50300
    assert resp.headers["retry-after"] == "5"
    after = _counters(client)
    assert after["db_unavailable_total"] == before["db_unavailable_total"] + 1
    assert after["db_pool_timeout_total"] == before["db_pool_timeout_total"]
    assert after["db_unretryable_failure_total"] == before["db_unretryable_failure_total"]


def test_after_commit_failure_is_not_retryable(client: TestClient) -> None:
    """**提交后**的数据库失败 → 500 且不带 Retry-After（写已落库，重试会重复写入）。

    回归防线：此前这条路径会回 503 + Retry-After: 5，客户端按指示重试就重复下单
    （复审实测复现：`orders` 1 → 2、库存二次扣减）。
    """

    app = client.app  # type: ignore[attr-defined]

    @app.post("/api/v1/qa-commit-then-fail", include_in_schema=False)
    def _route(db: DbSession) -> None:
        db.execute(text("SELECT 1"))
        db.commit()  # 提交成功 → session.info["committed"]，get_db 收尾时搬到 request.state
        raise DBOperationalError("SELECT 1", {}, Exception("connection lost after commit"))

    before = _counters(client)
    try:
        resp = client.post("/api/v1/qa-commit-then-fail")
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", "") != "/api/v1/qa-commit-then-fail"
        ]

    assert resp.status_code == 500, resp.text
    assert "retry-after" not in resp.headers
    assert "请勿重复提交" in resp.json()["msg"]
    after = _counters(client)
    assert after["db_unretryable_failure_total"] == before["db_unretryable_failure_total"] + 1
    assert after["db_unavailable_total"] == before["db_unavailable_total"]
    assert after["db_pool_timeout_total"] == before["db_pool_timeout_total"]


def test_unknown_commit_outcome_is_not_retryable(client: TestClient) -> None:
    """SQLSTATE 40003（提交结果未知）→ 500 无 Retry-After：可能已提交，不能诱导重试。"""
    from app.api.deps import get_db

    class _UnknownOutcome(Exception):
        sqlstate = "40003"

    def _unknown() -> None:
        raise DBOperationalError("COMMIT", {}, _UnknownOutcome("statement_completion_unknown"))

    app = client.app  # type: ignore[attr-defined]
    before = _counters(client)
    app.dependency_overrides[get_db] = _unknown
    try:
        resp = client.get("/api/v1/shop/products")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 500, resp.text
    assert "retry-after" not in resp.headers
    after = _counters(client)
    assert after["db_unretryable_failure_total"] == before["db_unretryable_failure_total"] + 1
    assert after["db_unavailable_total"] == before["db_unavailable_total"]


def test_snapshot_exposes_db_counters(client: TestClient) -> None:
    """概览监控卡片要能看到「数据库不可达」（原先只在 /metrics 里，看板看不到）。"""
    from app.core.metrics import snapshot

    data = snapshot()
    assert "db_unavailable_total" in data
    assert "db_unretryable_failure_total" in data


def test_engine_receives_statement_timeout() -> None:
    """engine 的连接参数里要真的带上 statement_timeout（配置值 > 0 时）。"""
    settings = get_settings()
    params = _pool_connect_params(engine)
    if engine.dialect.name == "sqlite":
        pytest.skip("SQLite 不设语句超时")
    if settings.db_statement_timeout_ms > 0:
        assert f"statement_timeout={settings.db_statement_timeout_ms}" in str(
            params.get("options", "")
        ), params


def test_statement_timeout_has_dedicated_counter(client: TestClient) -> None:
    """慢查询被掐断（SQLSTATE 57014）回 503，但计入专属计数，不混进「库不可用」。"""
    from app.api.deps import get_db

    class _QueryCanceled(Exception):
        sqlstate = "57014"

    def _slow() -> None:
        raise DBOperationalError("SELECT pg_sleep(30)", {}, _QueryCanceled("statement timeout"))

    app = client.app  # type: ignore[attr-defined]
    before = _counters(client)
    app.dependency_overrides[get_db] = _slow
    try:
        resp = client.get("/api/v1/shop/products")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503, resp.text
    after = _counters(client)
    name = "db_statement_timeout_total"
    assert after.get(name, 0.0) == before.get(name, 0.0) + 1, before
    assert after["db_unavailable_total"] == before["db_unavailable_total"]
    assert after["db_pool_timeout_total"] == before["db_pool_timeout_total"]
