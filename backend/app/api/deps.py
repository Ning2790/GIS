"""跨模块共用的 FastAPI 依赖。

放在 app/api 层而非某个模块内，避免 users / shop 等模块互相 import。

各模块路由请直接使用下面定义好的类型别名，不要自己写 `= Depends(...)`：
    def read_me(current_user: CurrentUser) -> dict: ...
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.modules.users import service as users_service
from app.modules.users.models import User, UserStatus

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """从 Authorization: Bearer <token> 解析出当前用户。

    令牌缺 exp/sub、签名错误、用户不存在，或被禁用 / 驳回等非正常状态，一律 401。
    """
    if credentials is None:
        raise UnauthorizedError()
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except Exception as exc:  # 令牌过期 / 签名错误 / 缺少 sub：统一按未认证处理
        raise UnauthorizedError("登录已过期，请重新登录") from exc
    try:
        user = users_service.get_user(db, user_id)
    except NotFoundError as exc:
        raise UnauthorizedError("登录已过期，请重新登录") from exc
    if user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("账号状态异常，请重新登录")
    return user


DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    """可选登录：无令牌、或带令牌但无效 / 账号异常，一律按**未登录（None）**处理。

    用于「公开内容 + 私有内容混合」的读取接口（文件读取、商品详情与推荐）：
    公开部分任何人可读，私有部分再按 None 判定（如私有文件 → 401）。
    过期的令牌不该让**公开页面**变成错误页——否则客户端带着旧令牌访问公开接口会拿到
    401、触发前端「会话失效」清理与跳登录（复审发现的回归：公开商品详情因此报错）。
    """
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except UnauthorizedError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_roles(*roles: str):
    """生成角色校验依赖。

    用法：``Annotated[User, Depends(require_roles("enterprise"))]``
    """

    def _checker(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise ForbiddenError("当前角色无权访问该功能")
        return current_user

    return _checker
