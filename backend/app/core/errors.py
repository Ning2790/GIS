"""统一错误码与业务异常。

业务代码抛出 AppError 及其子类，由 main.py 的异常处理器统一转成响应信封，
业务代码里不要自己拼 {"code": ...}。
"""

from fastapi import status


class ErrorCode:
    """业务错误码。0 表示成功，其余为各类失败。"""

    OK = 0
    BAD_REQUEST = 40000
    UNAUTHORIZED = 40100
    FORBIDDEN = 40300
    NOT_FOUND = 40400
    CONFLICT = 40900
    TOO_MANY_REQUESTS = 42900
    UNAVAILABLE = 50300
    INTERNAL = 50000


class AppError(Exception):
    """业务异常基类。"""

    def __init__(
        self,
        code: int,
        msg: str,
        http_status: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.code = code
        self.msg = msg
        self.http_status = http_status
        super().__init__(msg)


class BadRequestError(AppError):
    def __init__(self, msg: str) -> None:
        super().__init__(ErrorCode.BAD_REQUEST, msg, status.HTTP_400_BAD_REQUEST)


class UnauthorizedError(AppError):
    def __init__(self, msg: str = "未认证或登录已过期") -> None:
        super().__init__(ErrorCode.UNAUTHORIZED, msg, status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    def __init__(self, msg: str = "无权限执行该操作") -> None:
        super().__init__(ErrorCode.FORBIDDEN, msg, status.HTTP_403_FORBIDDEN)


class NotFoundError(AppError):
    def __init__(self, msg: str = "资源不存在") -> None:
        super().__init__(ErrorCode.NOT_FOUND, msg, status.HTTP_404_NOT_FOUND)


class ConflictError(AppError):
    def __init__(self, msg: str) -> None:
        super().__init__(ErrorCode.CONFLICT, msg, status.HTTP_409_CONFLICT)


class RateLimitError(AppError):
    """限流：配额用尽，携带 Retry-After 秒数（见 main.py 异常处理器）。"""

    def __init__(self, msg: str = "请求过于频繁，请稍后再试", retry_after: int = 60) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(ErrorCode.TOO_MANY_REQUESTS, msg, status.HTTP_429_TOO_MANY_REQUESTS)


class UnavailableError(AppError):
    """依赖服务不可用（如对象存储未配置 / 暂不可达）。"""

    def __init__(self, msg: str = "服务暂不可用，请稍后再试") -> None:
        super().__init__(ErrorCode.UNAVAILABLE, msg, status.HTTP_503_SERVICE_UNAVAILABLE)
