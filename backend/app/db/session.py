"""数据库引擎与会话。

这里另外承载一个**安全语义**：记录「本次请求是否已经提交过写事务」。数据库故障
（不可达 / 连接中断 / 等连接超时）统一按 503 返回，但**已经提交过**的请求如果再回
503 + Retry-After，客户端重试就可能重复写入（下单 / 售后 / 发消息等接口的幂等键是
可选的，前端也没有传）。因此：

- 会话在 `after_commit` 时打标记（`Session.info["committed"]`）；
- `get_db` 在收尾时把这个标记搬到 `request.state.db_committed`（跨线程池也能带出来——
  contextvar 在 anyio 线程里改了不会传回调用方，故走 `request.state`）；
- 异常处理器据此把「已提交后失败」降级为 **500 且不带 Retry-After**（明示勿重复提交），
  与「提交前失败」的 503 + Retry-After 区分开（见 app/main.py）。
"""

import logging
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def connect_args_for(
    database_url: str, connect_timeout: int, statement_timeout_ms: int = 0
) -> dict[str, object]:
    """按方言给出 `create_engine` 的连接参数。

    - SQLite：关闭同线程检查（FastAPI 用线程池执行同步依赖）；
    - PostgreSQL：**连接超时** `connect_timeout`（秒）。不设的话 libpq 用系统默认，
      数据库不可达时请求会长时间挂在建连上（实测挂到 253s 才失败），既占满工作线程池
      也占住连接池名额——依赖故障时应快速失败，交由上层按 503 处理；
      以及 **语句超时** `statement_timeout`（毫秒，0 表示不设）：一条慢查询会长期占住
      连接与工作线程，应用侧必须兜底（DB_CONNECT_TIMEOUT 只约束"连不上"，管不了"慢"）。

    取值注意：libpq 会把小于 2 的 connect_timeout 钳到 2 秒；`0` 或负值等于**不超时**（回到挂死）。
    statement_timeout 通过 `options=-c statement_timeout=<ms>` 传给会话（连接级缺省）。
    """
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    if database_url.startswith(("postgresql", "postgres")):
        args: dict[str, object] = {"connect_timeout": max(1, connect_timeout)}
        if statement_timeout_ms > 0:
            args["options"] = f"-c statement_timeout={statement_timeout_ms}"
        return args
    return {}


def build_engine(
    database_url: str,
    *,
    connect_timeout: int,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    statement_timeout_ms: int = 0,
) -> Engine:
    """按配置构建引擎（独立成函数，便于测试断言 connect_args 真的传了下去）。"""
    return create_engine(
        database_url,
        connect_args=connect_args_for(database_url, connect_timeout, statement_timeout_ms),
        future=True,
        # 取连接前探活，避免数据库重启后面的旧连接报错。
        pool_pre_ping=True,
        # 连接池大小与同步端点的默认线程池（anyio 40 线程）匹配：池太小会让请求排队等连接，
        # 太大则给 PostgreSQL 压力（注意 PG max_connections 是所有实例 / worker 的总和）。
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        # 小于常见网络中间件的空闲断连时间，主动回收旧连接。
        pool_recycle=1800,
    )


engine = build_engine(
    settings.database_url,
    connect_timeout=settings.db_connect_timeout,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    statement_timeout_ms=settings.db_statement_timeout_ms,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(Session, "after_commit")
def _mark_committed(session: Session, **_kwargs: object) -> None:
    """提交成功即打标记：此后本请求再遇到数据库异常都不允许诱导重试。"""
    session.info["committed"] = True


def get_db(request: Request) -> Generator[Session]:
    """FastAPI 依赖：按请求提供数据库会话，并把「是否已提交过写事务」带到 request.state。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        if db.info.get("committed"):
            # 走 request.state 而非 contextvar：同步端点在线程池里执行，
            # 线程内 set 的 contextvar 不会传回事件循环。
            request.state.db_committed = True
        db.close()


def init_db() -> None:
    """按模型建表。

    仅用于本地开发与测试；正式环境的数据结构变更走 Alembic 迁移。
    """
    import app.db.models_registry  # noqa: F401  注册所有模型
    from app.db.base import Base

    Base.metadata.create_all(bind=engine)


def request_committed(request: Request) -> bool:
    """本次请求是否已经提交过写事务（供异常处理器判断能否让客户端重试）。"""
    return bool(getattr(request.state, "db_committed", False))
