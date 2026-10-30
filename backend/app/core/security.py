"""密码哈希与 JWT 签发 / 校验。"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import BadRequestError

# bcrypt 的输入上限是 72 字节；超出时直接给业务错误，不要让它变成 500。
_BCRYPT_MAX_BYTES = 72


def hash_password(raw: str) -> str:
    """生成密码哈希。数据库只存哈希，绝不存明文。"""
    try:
        return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    except ValueError as exc:
        raise BadRequestError(f"密码过长（最多 {_BCRYPT_MAX_BYTES} 字节）") from exc


def verify_password(raw: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配。哈希损坏时返回 False，不抛异常。"""
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, role: str) -> str:
    """签发访问令牌。subject 为用户 ID 字符串。"""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """解析访问令牌。

    令牌非法、过期，或缺少 exp / sub 声明时抛出 jwt 异常，由调用方转成业务错误；
    强制要求 exp 与 sub，避免「不带过期时间的令牌永久有效」。
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
