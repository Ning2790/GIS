"""FastAPI 应用入口。

启动：uv run uvicorn app.main:app --reload --port 8000
文档：http://127.0.0.1:8000/docs
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DataError as DBDataError
from sqlalchemy.exc import DisconnectionError as DBDisconnectionError
from sqlalchemy.exc import OperationalError as DBOperationalError
from sqlalchemy.exc import TimeoutError as DBTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core import metrics
from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode, RateLimitError
from app.core.input_guard import InputGuardMiddleware
from app.core.logging import request_id_var, setup_logging
from app.core.metrics import MetricsMiddleware
from app.core.queue_gate import QueueGateMiddleware
from app.core.request_context import RequestContextMiddleware, request_id_of
from app.core.response import fail, ok
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.session import request_committed

settings = get_settings()
logger = logging.getLogger(__name__)

# PostgreSQL SQLSTATE：提交结果未知（此时**不能**让客户端重试——可能已经提交成功）
_SQLSTATE_UNKNOWN_OUTCOME = "40003"
# 慢查询被 statement_timeout 掐断（PostgreSQL query_canceled）
_SQLSTATE_STATEMENT_TIMEOUT = "57014"


def _sqlstate_of(exc: Exception) -> str | None:
    """取底层 DBAPI 异常的 SQLSTATE（psycopg 挂在 `exc.orig.sqlstate` 上；取不到返回 None）。"""
    return getattr(getattr(exc, "orig", None), "sqlstate", None)


# 框架级 HTTP 错误的默认提示（404 / 405 等此前是 Starlette 英文文案）
_HTTP_ERROR_MESSAGES = {
    401: "未认证或登录已过期",
    403: "无权限执行该操作",
    404: "资源不存在",
    405: "请求方法不允许",
}


def create_app() -> FastAPI:
    setup_logging()
    docs_enabled = settings.env == "dev"  # 生产关闭交互式文档，减少暴露面

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="青海旅游 + 农产品平台后端接口。所有响应统一为 {code, msg, data} 信封。",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # 先 add 队列闸门、后 add CORS：后 add 的在外层（CORS 最外）——
    # 闸门拒绝的 503 也会带跨域头，前端才能读到排队提示。
    # 指标中间件在闸门外层：排队拒绝（503）也要计入指标（N10）。
    app.add_middleware(QueueGateMiddleware)
    # 输入防护在 CORS 内侧（错误响应也带跨域头）、在闸门外侧（明显非法请求不占队列名额）。
    app.add_middleware(InputGuardMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # 跨域前端要用 X-Request-ID 排障、读导出截断标记时必须显式暴露（默认只暴露简单响应头）
        expose_headers=["X-Request-ID", "X-Export-Rows", "X-Export-Truncated"],
    )
    if not docs_enabled:
        # 最外层：生产环境所有响应（含闸门 503 / CORS 预检）都带安全头
        app.add_middleware(SecurityHeadersMiddleware)

    # 最外层（N8）：请求 ID 与慢请求日志要覆盖全部请求与响应（含闸门 / 安全头产生的响应），
    # 并在响应头回带 X-Request-ID——故放在最后 add（后 add 的在外层）。
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        headers = None
        if isinstance(exc, RateLimitError):
            headers = {"Retry-After": str(exc.retry_after)}
        return JSONResponse(
            status_code=exc.http_status, content=fail(exc.code, exc.msg), headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder(fail(ErrorCode.BAD_REQUEST, "参数校验失败", exc.errors())),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """框架级 401/403/404/405 等也统一成 {code,msg,data} 信封。"""
        code = {
            401: ErrorCode.UNAUTHORIZED,
            403: ErrorCode.FORBIDDEN,
            404: ErrorCode.NOT_FOUND,
        }.get(exc.status_code, ErrorCode.BAD_REQUEST)
        msg = _HTTP_ERROR_MESSAGES.get(exc.status_code, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=fail(code, msg))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """兜底：未捕获异常记录日志并返回信封，不把堆栈泄给客户端。

        注意这里在**所有中间件之外**（Starlette 的 ServerErrorMiddleware 兜底），
        日志上下文的 contextvar 已还原——请求 ID 从 `request.state` 取，
        并显式作为响应头回带（否则 500 响应完全无法与其它日志关联）。
        """
        request_id = request_id_of(request)
        token = request_id_var.set(request_id)  # 让这条日志带上正确的 request_id 字段
        try:
            logger.exception("未处理异常（req=%s）：%s", request_id, exc)
        finally:
            request_id_var.reset(token)
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL, "服务内部错误"),
            headers={"X-Request-ID": request_id},
        )

    def _db_failure_response(
        request: Request, exc: Exception, *, busy_msg: str, retry_after: int, overload: bool
    ) -> JSONResponse:
        """数据库层失败的统一响应：**区分「能不能重试」**。

        - 本次请求**已经提交过写事务**（`get_db` 把标记放到 `request.state`）→ 回 500
          且**不带 Retry-After**：写已经落库了，再让客户端重试就是重复写入（下单 /
          售后 / 发消息等接口的幂等键可选、前端也没传）。文案明确「请勿重复提交」。
        - SQLSTATE `40003`（statement_completion_unknown，提交结果未知）同理不可重试。
        - 其余情况（提交前失败）才按「繁忙 / 暂不可用」回 503 + Retry-After。
        """
        if request_committed(request) or _sqlstate_of(exc) == _SQLSTATE_UNKNOWN_OUTCOME:
            metrics.db_unretryable_failure_total.inc()
            logger.error("数据库失败且本次操作已提交/结果未知（禁止重试，避免重复写入）：%s", exc)
            return JSONResponse(
                status_code=500,
                content=fail(ErrorCode.INTERNAL, "操作已受理，但结果回传失败，请勿重复提交"),
            )
        if _sqlstate_of(exc) == _SQLSTATE_STATEMENT_TIMEOUT:
            # 慢查询被我们自己的 statement_timeout 掐断：仍是可重试的「忙」，但要与
            # 「库不可用 / 池超时」分开计数——看到它涨该去优化慢查询，而不是查数据库。
            metrics.db_statement_timeout_total.inc()
            logger.warning("慢查询被语句超时掐断（statement_timeout）：%s", exc)
        elif overload:
            metrics.db_pool_timeout_total.inc()
            logger.warning("数据库连接池等连接超时（过载）：%s", exc)
        else:
            metrics.db_unavailable_total.inc()
            logger.error("数据库不可用（依赖故障）：%s", exc)
        return JSONResponse(
            status_code=503,
            content=fail(ErrorCode.UNAVAILABLE, busy_msg),
            headers={"Retry-After": str(retry_after)},
        )

    @app.exception_handler(DBDataError)
    async def handle_db_data_error(request: Request, exc: DBDataError) -> JSONResponse:
        """数据库驱动拒绝输入（非法字符 / 数值越界）：按客户端错误回 422，不再落成 500。

        中间件已拦截路径 / 查询 / JSON 体中的 NUL；这里是方言差异与 multipart 等
        未覆盖入口的兜底（例如超大整数与 int4 列比较、SQLite 对控制字符更宽松）。
        """
        logger.warning("数据库拒绝输入（DataError）：%s", exc)
        return JSONResponse(
            status_code=422,
            content=fail(ErrorCode.BAD_REQUEST, "输入包含非法字符或超出支持范围"),
        )

    @app.exception_handler(DBTimeoutError)
    async def handle_db_pool_timeout(request: Request, exc: DBTimeoutError) -> JSONResponse:
        """连接池等连接超时：属**过载**（承载）而非服务缺陷，按排队语义回 503 + Retry-After。

        压测实测（见 docs/压测报告.md）：单机突发下交易类在途容量可大于连接池能服务的
        并发数，等连接超时的请求原本落成 500——客户端会当成故障、也不会重试，语义错位；
        统一按「繁忙，稍后重试」回，与排队闸门 / 限流同一种失败语义。

        注意：**提交之后**的失败不走 503（见 `_db_failure_response`），否则重试会重复写入。
        """
        return _db_failure_response(
            request, exc, busy_msg="服务繁忙，请稍后重试", retry_after=1, overload=True
        )

    async def handle_db_unavailable(request: Request, exc: Exception) -> JSONResponse:
        """数据库不可达 / 连接中断：**依赖故障**，同样按 503 + Retry-After（提交前才敢让重试）。

        与池超时（过载）分开计数：`db_unavailable_total` 才是「数据库挂了」的告警信号；
        `db_pool_timeout_total` 高而它不动，说明只是并发太猛。反过来说，库停机时两者都会
        涨——`DB_CONNECT_TIMEOUT` 默认小于 `DB_POOL_TIMEOUT`，就是为了让「连不上」先暴露。

        覆盖范围仅限数据库：Redis 是刻意的 fail-open 降级（限流/缓存不可用时放行，见
        `core/rate_limit.py`），MinIO 不可用由 files 模块自行回 503（`UnavailableError`）。
        """
        return _db_failure_response(
            request, exc, busy_msg="服务暂不可用，请稍后重试", retry_after=5, overload=False
        )

    # Starlette 按 MRO 精确查表，注册多个异常类要分别登记（不能传元组）。
    # DisconnectionError 是防御性注册：SQLAlchemy 主要由连接池的 checkout 钩子抛它，
    # 现实中「连接被掐断」多由 psycopg 抛 OperationalError（已被下一行覆盖）。
    app.add_exception_handler(DBOperationalError, handle_db_unavailable)
    app.add_exception_handler(DBDisconnectionError, handle_db_unavailable)

    @app.get("/", tags=["meta"], summary="服务信息")
    def index() -> dict:
        return ok({"app": settings.app_name, "docs": "/docs"})

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        """Prometheus 文本指标（不经统一响应信封）。

        部署时由网关（deploy/nginx.conf）限制为**内网可读**，不对公网暴露。
        """
        return Response(
            content=metrics.render_latest(), media_type=metrics.prometheus_content_type()
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    def custom_openapi() -> dict:
        """契约与实现对齐：422 统一声明为 {code,msg,data} 信封（而非 FastAPI 默认 detail）。"""
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=settings.app_name,
            version="0.1.0",
            description="青海旅游 + 农产品平台后端接口。所有响应统一为 {code, msg, data} 信封。",
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.setdefault(
            "ErrorEnvelope",
            {
                "type": "object",
                "properties": {
                    "code": {"type": "integer"},
                    "msg": {"type": "string"},
                    "data": {"nullable": True},
                },
                "required": ["code", "msg"],
            },
        )
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                response = operation.get("responses", {}).get("422")
                if response is not None:
                    response["content"] = {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorEnvelope"}
                        }
                    }
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()
