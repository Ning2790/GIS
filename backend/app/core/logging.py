"""日志配置（N8）：开发可读格式、生产 JSON 单行；请求 ID 贯穿 + 敏感信息脱敏。

设计要点：
- **开发（ENV=dev）**：`时间 级别 logger: 消息 [req <id>]`，人眼看；
- **生产（ENV != dev）**：JSON 单行（`ts / level / logger / msg / request_id` + 请求元信息
  `method / path / status / duration_ms`），便于 Loki / ELK 采集并**按 request_id 串联**；
- **请求 ID**：由 `RequestContextMiddleware`（`core/request_context.py`）写入 contextvar，
  这里的 `RequestContextFilter` 把它塞进每条日志——同一次请求的所有日志都能 grep 出来；
- **脱敏**：在 **Formatter 出口**统一做（不再就地改写 record），因此
  ① 不依赖 handler 注册顺序、② 其它消费者（测试 / 未来的异步 handler）拿到的 record 保持原样、
  ③ **异常堆栈同样脱敏**（`logger.exception` 的 traceback 里常带 SQL 绑定参数等原始值）。

覆盖范围：本装配由 `app.main:create_app` 与 `app.worker`（Celery）调用；`scripts/*.py`
用 print 输出，不在本口径内。
"""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# 当前请求上下文（由 RequestContextMiddleware 设置；非请求线程取默认值）
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
# 元信息默认 None（不能用可变默认值：B039），读取处统一 `or {}`
request_meta_var: ContextVar[dict[str, Any] | None] = ContextVar("request_meta", default=None)

# ---- 脱敏规则 ----
# 手机号：可带 +86 前缀与空格/点/横线分隔；匹配前先做全角数字归一化
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[\s-]?)?1[3-9](?:[\s.\-]?\d){9}(?!\d)")
# Bearer 令牌
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[\w.\-]{8,}")
# key=value / key: value 形态的凭据（token=xxx、access_token: xxx、?token=abc、password=...）
_SECRET_PAIR_RE = re.compile(
    r"(?i)\b(access_token|refresh_token|token|api_key|apikey|password|secret|authorization)\b"
    r"(\s*[:=]\s*)([\"']?)([^\s\"'&,;)]{4,})"
)
# JWT（三段式，header 恒以 eyJ 开头）
_JWT_RE = re.compile(r"\beyJ[\w-]{4,}\.[\w-]{4,}\.[\w-]{4,}")
# 长十六进制串（refresh token 之类）；≥40 位以免误伤 32 位业务标识（如 family_id=token_hex(16)）
_HEX_RE = re.compile(r"\b[0-9a-f]{40,}\b", re.IGNORECASE)
# 长「随机串」（base64url 风格：≥40 位且大小写数字混合，如 token_urlsafe 的结果）
_OPAQUE_RE = re.compile(
    r"(?=[A-Za-z0-9_-]{40,})(?=[A-Za-z0-9_-]*[A-Z])(?=[A-Za-z0-9_-]*[a-z])"
    r"(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{40,}"
)


def mask_sensitive(text: str, keep: tuple[str, ...] = ()) -> str:
    """脱敏手机号与凭据类字符串；`keep` 里的串原样保留（如当前请求 ID）。

    规则覆盖面见模块级常量注释：手机号保留前 3 后 4，其余整体替换为 `<token>`。
    """
    text = text.translate(_FULLWIDTH_DIGITS)
    sentinels: dict[str, str] = {}
    for index, token in enumerate(keep):
        if token and token != "-" and token in text:
            sentinel = f"\x00keep{index}\x00"
            text = text.replace(token, sentinel)
            sentinels[sentinel] = token

    def _phone(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group())
        return f"{digits[:3]}****{digits[-4:]}"  # 保留前 3 后 4（+86 前缀一并去掉）

    text = _PHONE_RE.sub(_phone, text)
    text = _BEARER_RE.sub(r"\1<token>", text)
    text = _SECRET_PAIR_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}<token>", text)
    text = _JWT_RE.sub("<token>", text)
    text = _HEX_RE.sub("<token>", text)
    text = _OPAQUE_RE.sub("<token>", text)
    for sentinel, token in sentinels.items():
        text = text.replace(sentinel, token)
    return text


class RequestContextFilter(logging.Filter):
    """把当前请求的 request_id 与元信息注入每条日志记录（供 Formatter 取字段）。

    元信息写进 record（而不只留在 contextvar）是为了**跨线程/异步 handler 安全**：
    将来若引入 `QueueHandler`（日志先入队、由别的线程格式化），contextvar 在那边已还原，
    只有 record 上的字段还在。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        meta = request_meta_var.get() or {}
        for key in ("method", "path", "status", "duration_ms"):
            if key in meta:
                setattr(record, key, meta[key])
        return True


class JsonFormatter(logging.Formatter):
    """生产格式：单行 JSON（采集友好）；`msg` 与 `exc` 都脱敏。"""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "-")
        keep = (request_id,)
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": mask_sensitive(record.getMessage(), keep),
            "request_id": request_id,
        }
        meta = request_meta_var.get() or {}
        for key in ("method", "path", "status", "duration_ms"):
            # 优先取 record 上的字段（异步 handler 场景 contextvar 已还原，见 RequestContextFilter）
            value = getattr(record, key, None)
            if value is None:
                value = meta.get(key)
            if value is not None:
                # 元信息同样要脱敏：URL 里可能带手机号等敏感片段（如被扫的路径）
                payload[key] = mask_sensitive(value, keep) if isinstance(value, str) else value
        if record.exc_info:
            # 异常堆栈里常带原始值（SQL 绑定参数 / 校验输入），必须一并脱敏
            payload["exc"] = mask_sensitive(self.formatException(record.exc_info), keep)
        return json.dumps(payload, ensure_ascii=False)


class ReadableFormatter(logging.Formatter):
    """开发格式：`时间 级别 logger: 消息 [req <id>]`，整行（含堆栈）脱敏。"""

    def format(self, record: logging.LogRecord) -> str:
        request_id = getattr(record, "request_id", "-")
        base = super().format(record)
        if request_id and request_id != "-":
            base = f"{base} [req {request_id}]"
        return mask_sensitive(base, (request_id,))


def setup_logging(level: int = logging.INFO) -> None:
    """按 ENV 装配根日志：dev 可读、非 dev JSON；脱敏与请求 ID 随 Formatter 生效。

    API 进程（`app.main`）与 Celery worker（`app.worker`）都调用本函数；uvicorn 自带的
    handler 会被清掉并改为向根 logger 传播，否则它的访问日志既不脱敏也不带 request_id。
    """
    from app.core.config import get_settings

    settings = get_settings()
    is_prod = settings.env != "dev"
    formatter: logging.Formatter = (
        JsonFormatter()
        if is_prod
        else ReadableFormatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()  # 重复调用（测试 / 多次 create_app）不叠加 handler
    root.addHandler(handler)
    root.setLevel(level)

    # uvicorn 在导入应用前就装好了自己的 handler；不清掉的话访问日志会绕过本装配
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
