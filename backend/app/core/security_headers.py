"""生产环境安全响应头（S10 加固）。

网关层（deploy/nginx/nginx.conf）已有一份；这里做**应用层兜底**——后端端口
被直接访问、或更换网关时同样带上安全头。仅在非 dev 环境注册（避免干扰本地调试）。
只补充缺失的头，不覆盖应用 / 中间件已设置的值。
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=31536000"),
)


class SecurityHeadersMiddleware:
    """给所有 HTTP 响应追加安全头。"""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _value in headers}
                for key, value in _HEADERS:
                    if key not in existing:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, _send)
