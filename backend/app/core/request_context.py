"""请求上下文（N8）：X-Request-ID 贯穿 + 慢请求日志。

- **请求 ID**：入站 `X-Request-ID` **合法则复用**（网关 nginx 的 `$request_id` 是 32 位 hex，
  这样网关访问日志与后端日志能对上同一条请求），不合法则生成一个；响应头回带同一个 ID，
  客户端反馈问题时可直接给出。
- **慢请求**：超过 `SLOW_REQUEST_MS`（默认 500ms）记 warning，含方法 / 路径 / 耗时，
  并经 `core/logging.py` 的 Formatter 带上 request_id——过载排查时先看这些行。
  SSE（`text/event-stream`）不算慢：流式响应天然持续数秒，记 warning 只会稀释信号。
- 中间件注册为**最外层**（见 main.py 的 add 顺序）：排队闸门拒绝的 503 也要有请求 ID，
  且耗时统计覆盖「从进进程到返回」的完整时长。
- 请求 ID 同时写入 `scope["state"]`：**未处理异常（500）**由 Starlette 的
  ServerErrorMiddleware 在所有用户中间件之外兜底，那时 contextvar 已还原，
  兜底处理器只能从 `request.state` 取（见 `request_id_of`）。
"""

import logging
import re
import time
import uuid

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.logging import request_id_var, request_meta_var

REQUEST_ID_HEADER = b"x-request-id"

# 合法 ID：8–128 位 [A-Za-z0-9._:-]。既容纳 nginx $request_id / uuid / traceparent 风格，
# 又挡掉换行与控制字符（防止日志注入；fullmatch 保证尾部换行也不放行）。
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._:-]{8,128}")

logger = logging.getLogger("app.access")


def resolve_request_id(incoming: str | None) -> str:
    """复用合法的入站请求 ID，否则生成新的（32 位十六进制）。"""
    if incoming and _REQUEST_ID_RE.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def request_id_of(request: Request) -> str:
    """取本次请求 ID（供**未处理异常**的兜底处理器使用）。

    500 由 ServerErrorMiddleware 在最外层处理，此时 contextvar 已还原完毕，
    只能从 scope（`request.state`）里读。
    """
    return getattr(request.state, "request_id", "-")


class RequestContextMiddleware:
    """建立请求日志上下文（含 request_id），并在超阈值时记慢请求。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = dict(scope.get("headers") or [])
        incoming = raw_headers.get(REQUEST_ID_HEADER, b"").decode("latin-1", "ignore")
        request_id = resolve_request_id(incoming or None)
        method = scope.get("method", "")
        path = scope.get("path", "")
        # 兜底处理器（500）在中间件之外运行，需要从 scope 取 ID
        scope.setdefault("state", {})["request_id"] = request_id

        id_token = request_id_var.set(request_id)
        meta_token = request_meta_var.set({"method": method, "path": path})

        status = 500
        is_stream = False
        started = time.perf_counter()

        async def send_wrapper(message: dict) -> None:
            nonlocal status, is_stream
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message.setdefault("headers", [])
                headers.append((REQUEST_ID_HEADER, request_id.encode()))
                is_stream = any(
                    name.lower() == b"content-type" and b"text/event-stream" in value.lower()
                    for name, value in headers
                )
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000)
            meta = dict(request_meta_var.get() or {})
            meta.update({"status": status, "duration_ms": duration_ms})
            request_meta_var.set(meta)
            threshold = get_settings().slow_request_ms
            if not is_stream and threshold > 0 and duration_ms >= threshold:
                logger.warning(
                    "慢请求 %s %s → %s 用时 %dms（阈值 %dms）",
                    method,
                    path,
                    status,
                    duration_ms,
                    threshold,
                )
            else:
                logger.debug("%s %s → %s 用时 %dms", method, path, status, duration_ms)
            request_id_var.reset(id_token)
            request_meta_var.reset(meta_token)
