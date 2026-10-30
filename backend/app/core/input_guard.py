"""请求输入防护：拒绝会让数据库 / 驱动抛异常的输入（NUL 与 C0 控制字符、超 int32 路径 ID）。

为什么放在 ASGI 中间件而不是逐字段校验：
- 路径 / 查询参数覆盖所有端点，逐个加 `AfterValidator` 容易漏；
- JSON 请求体在中间件里缓冲后解析（`\\u0000` 转义解析后就是 NUL 字符），
  避免 30+ 个请求 schema 全部改基类；
- Multipart 文件名无法在中间件里廉价解析，由 files 模块单独校验。

三层配合：
1. 本中间件 → 客户端输入错误在路由前返回 422；
2. files 模块 → multipart 文件名控制字符返回 400；
3. `main.py` 的 `DataError` 处理器 → 数据库层兜底 422（兼容 SQLite / PG 方言差异）。
"""

import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qsl

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# NUL + 除 \t \n \r 外的 C0 控制字符 + DEL；这些字符进 PostgreSQL text 会直接报错
_FORBIDDEN_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_INT4_MAX = 2_147_483_647
# JSON 请求体缓冲上限：本项目请求体都很小（上传走 multipart，不在此列）
_MAX_JSON_BODY = 1_048_576


def has_forbidden_chars(value: str) -> bool:
    return _FORBIDDEN_CHARS.search(value) is not None


def payload_has_forbidden_chars(value: object) -> bool:
    """递归检查 JSON 值中的字符串键与值。"""
    if isinstance(value, str):
        return has_forbidden_chars(value)
    if isinstance(value, Mapping):
        return any(
            payload_has_forbidden_chars(key) or payload_has_forbidden_chars(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(payload_has_forbidden_chars(item) for item in value)
    return False


def _json_response(status: int, msg: str) -> tuple[list[tuple[bytes, bytes]], bytes]:
    body = json.dumps({"code": 40000, "msg": msg, "data": None}, ensure_ascii=False).encode("utf-8")
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    return headers, body


async def _send_rejection(send: Send, status: int, msg: str) -> None:
    headers, body = _json_response(status, msg)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class InputGuardMiddleware:
    """纯 ASGI 中间件：在路由前拦截明显非法输入，避免落到 DB 驱动变成 500。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if has_forbidden_chars(path):
            await _send_rejection(send, 422, "请求路径包含非法字符")
            return
        for segment in path.split("/"):
            if segment.isdigit() and int(segment) > _INT4_MAX:
                await _send_rejection(send, 422, "资源编号超出范围")
                return

        query = scope.get("query_string", b"").decode("latin-1")
        for _, value in parse_qsl(query, keep_blank_values=True, encoding="utf-8"):
            if has_forbidden_chars(value):
                await _send_rejection(send, 422, "查询参数包含非法字符")
                return

        headers = dict(scope.get("headers") or [])
        content_type = headers.get(b"content-type", b"").decode("latin-1").lower()
        method = scope.get("method", "GET")
        if not (
            content_type.startswith("application/json")
            and method in ("POST", "PUT", "PATCH", "DELETE")
        ):
            await self.app(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > _MAX_JSON_BODY:
                await _send_rejection(send, 422, "请求体过大")
                return
            if not message.get("more_body", False):
                break

        if body:
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                # 非法 JSON 交给 FastAPI 统一返回 422，不在这里重复造轮子
                payload = None
            if payload is not None and payload_has_forbidden_chars(payload):
                await _send_rejection(send, 422, "请求体包含非法字符")
                return

        replayed = False
        body_bytes = bytes(body)

        async def receive_replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}
            return await receive()

        await self.app(scope, receive_replay, send)
