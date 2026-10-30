"""并发 e2e 测试夹具：真实 PostgreSQL + Redis + 进程内 uvicorn。

与 tests/ 的单元测试不同，本目录**不在** SQLite 夹具环境里运行：使用真实
PostgreSQL / Redis，并以真实 HTTP 请求验证并发行为——SQLite 单连接 + TestClient
无法复现多连接并发竞争（详见 docs/代码审计报告.md）。

**数据隔离**：每次运行创建临时数据库 `qh_e2e_<随机>` 并跑迁移，结束后删除；
Redis 切到独立的第 5 号库并在首尾清空。这样 e2e 不会写入演示库（此前直接使用
根 .env 的库，跑一次就留下 e2e-* 商品 / 账号，污染演示数据）。

运行：``make e2e``（或 cd backend && uv run pytest tests_e2e -q）
前置：``docker compose up -d``；本目录不要与 tests/ 混跑
（tests/conftest.py 会把进程内配置覆盖为 SQLite / 无 Redis）。
"""

import logging
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

# httpx 每个请求会打 INFO 日志，并发用例下噪音太大
logging.getLogger("httpx").setLevel(logging.WARNING)

if os.environ.get("DATABASE_URL", "").startswith("sqlite"):
    raise RuntimeError(
        "tests_e2e 需要真实的 PostgreSQL/Redis，它不是单元测试的一部分："
        "请单独运行 `uv run pytest tests_e2e`（不要与 tests/ 混跑）"
    )

# e2e 的全部流量来自本机（同一 IP）：注册 / 登录按 IP 限流会误伤测试自身，
# 调高这两档（setdefault：显式配置优先）。
os.environ.setdefault("RATE_LIMIT_REGISTER_PER_MINUTE", "100000")
os.environ.setdefault("RATE_LIMIT_LOGIN_PER_MINUTE", "100000")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from uvicorn import Config, Server  # noqa: E402

from app.core.config import get_settings  # noqa: E402

settings = get_settings()
E2E_REDIS_DB = 5  # 与演示库的 Redis 0 号库隔离


def _require_services() -> None:
    """数据库 / Redis 不可用时明确跳过（普通开发环境不因此阻塞）。"""
    if not settings.database_url.startswith("postgresql"):
        pytest.skip("tests_e2e 需要 PostgreSQL：请配置根 .env 并 docker compose up -d")
    try:
        probe = create_engine(settings.database_url, connect_args={"connect_timeout": 3})
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
        probe.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL 不可连接（{exc}）：先 docker compose up -d")
    if not settings.redis_url:
        pytest.skip("REDIS_URL 未配置：并发测试需要库存闸门真实生效")
    try:
        import redis as redis_lib

        redis_lib.Redis.from_url(settings.redis_url, socket_connect_timeout=3).ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis 不可连接（{exc}）：先 docker compose up -d")


def _redis_test_url(base_url: str) -> str:
    """把 redis URL 的库号换成独立库（保留密码 / 主机 / 端口）。"""
    prefix, _, _ = base_url.rpartition("/")
    return f"{prefix}/{E2E_REDIS_DB}"


@pytest.fixture(scope="session", autouse=True)
def isolated_database() -> Iterator[None]:
    """创建临时 PG 库 + 独立 Redis 库，并把进程内配置指过去；结束后清理。"""
    _require_services()
    base_url = make_url(settings.database_url)
    db_name = f"qh_e2e_{uuid.uuid4().hex[:10]}"
    admin_url = base_url.set(database="postgres").render_as_string(hide_password=False)
    test_url = base_url.set(database=db_name).render_as_string(hide_password=False)

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    # 演示库依赖 PostGIS（attractions.geom）；新库要显式装扩展后再跑迁移
    setup_engine = create_engine(test_url, isolation_level="AUTOCOMMIT")
    with setup_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    setup_engine.dispose()

    redis_url = _redis_test_url(settings.redis_url) if settings.redis_url else ""
    os.environ["DATABASE_URL"] = test_url
    if redis_url:
        os.environ["REDIS_URL"] = redis_url
    get_settings.cache_clear()

    backend_root = Path(__file__).resolve().parents[1]
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_root,
        env={**os.environ, "DATABASE_URL": test_url},
        capture_output=True,
        text=True,
    )

    import redis as redis_lib

    redis_client = redis_lib.Redis.from_url(redis_url) if redis_url else None
    if redis_client is not None:
        redis_client.flushdb()

    if migration.returncode != 0:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()
        raise RuntimeError(f"e2e 临时库迁移失败：\n{migration.stdout}\n{migration.stderr}")

    # 景点是行程 / 地图用例的前置数据（空库时街道测试会跳过）；只灌演示景点，不灌用户
    seed = subprocess.run(
        [sys.executable, "scripts/seed_travel.py"],
        cwd=backend_root,
        env={**os.environ, "DATABASE_URL": test_url},
        capture_output=True,
        text=True,
    )
    if seed.returncode != 0:
        raise RuntimeError(f"e2e 临时库灌景点失败：\n{seed.stdout}\n{seed.stderr}")

    yield

    if redis_client is not None:
        redis_client.flushdb()
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
    admin_engine.dispose()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="session")
def api(isolated_database: None) -> httpx.Client:
    """起真实 uvicorn（后台线程），返回指向 /api/v1 的 HTTP 客户端。

    app 在临时库 / Redis 配置生效后才导入，避免引擎按演示库初始化。
    """
    from app.main import app

    port = _free_port()
    server = Server(Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=f"{root}/api/v1", timeout=30)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            if client.get(f"{root}/").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        server.should_exit = True
        client.close()
        raise RuntimeError("uvicorn 测试服务启动超时")
    yield client
    client.close()
    server.should_exit = True
    thread.join(timeout=10)


@pytest.fixture(scope="session")
def db(isolated_database: None) -> sessionmaker:
    """直连**临时测试库**的会话工厂（状态准备与断言用）。"""
    engine = create_engine(get_settings().database_url, future=True)
    factory = sessionmaker(bind=engine, future=True)
    yield factory
    engine.dispose()
