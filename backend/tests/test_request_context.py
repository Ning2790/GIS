"""结构化日志与请求追踪（N8）：X-Request-ID、慢请求日志、脱敏、生产 JSON 格式。"""

import json
import logging

from fastapi.testclient import TestClient

from app.core import logging as logging_module
from app.core.config import get_settings
from app.core.logging import (
    JsonFormatter,
    ReadableFormatter,
    RequestContextFilter,
    mask_sensitive,
    request_id_var,
    request_meta_var,
)
from app.core.request_context import resolve_request_id


def _capture(logger_name: str) -> tuple[list[logging.LogRecord], logging.Handler, int]:
    """挂一个收集 record 的 handler；返回 (records, handler, 原日志级别)。

    调用方需在 finally 里 `removeHandler` + `setLevel(原级别)`，避免污染同一进程的其它测试。
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    target = logging.getLogger(logger_name)
    previous_level = target.level
    handler = _Collector()
    handler.addFilter(RequestContextFilter())  # 与线上装配一致（Formatter 负责脱敏）
    target.addHandler(handler)
    target.setLevel(logging.DEBUG)
    return records, handler, previous_level


def _release(logger_name: str, handler: logging.Handler, level: int) -> None:
    target = logging.getLogger(logger_name)
    target.removeHandler(handler)
    target.setLevel(level)


def test_response_carries_generated_request_id(client: TestClient) -> None:
    """每个响应都回带 X-Request-ID；未传时自动生成 32 位十六进制。"""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    request_id = resp.headers["x-request-id"]
    assert len(request_id) == 32
    assert request_id.isalnum()


def test_incoming_valid_request_id_is_reused(client: TestClient) -> None:
    """合法的入站请求 ID 复用（网关 $request_id / 客户端追踪），回带同一个。"""
    incoming = "6f1c2d9a4b7e48f0a1b2c3d4e5f60718"
    resp = client.get("/api/v1/health", headers={"X-Request-ID": incoming})
    assert resp.headers["x-request-id"] == incoming


def test_illegal_request_id_is_replaced(client: TestClient) -> None:
    """非法请求 ID（过短 / 含注入字符 / 尾随换行）一律丢弃并生成新的。"""
    for bad in ("short", "bad id with spaces", "line\nbreak\ninjection", "x" * 200, "aaaaaaaa\n"):
        resp = client.get("/api/v1/health", headers={"X-Request-ID": bad})
        got = resp.headers["x-request-id"]
        assert got != bad
        assert len(got) == 32


def test_unhandled_error_keeps_request_id(client: TestClient) -> None:
    """未处理异常（500）同样带 X-Request-ID，且日志里能按该 ID 找到请求。

    500 由 Starlette 的 ServerErrorMiddleware 在最外层兜底——那时中间件的 contextvar
    已还原，必须靠 scope 里的 request_id 才能关联（回归防线）。
    """
    app = client.app  # type: ignore[attr-defined]
    incoming = "deadbeefdeadbeefdeadbeefdeadbeef"

    async def _boom() -> None:
        raise RuntimeError("测试用爆炸 13800138000")

    app.add_api_route("/api/v1/qa-boom", _boom, methods=["GET"], include_in_schema=False)
    records, handler, level = _capture("app.main")
    try:
        with TestClient(app, raise_server_exceptions=False) as raw_client:
            resp = raw_client.get("/api/v1/qa-boom", headers={"X-Request-ID": incoming})
    finally:
        _release("app.main", handler, level)
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", "") != "/api/v1/qa-boom"
        ]

    assert resp.status_code == 500, resp.text
    assert resp.headers["x-request-id"] == incoming
    hits = [r for r in records if getattr(r, "request_id", "-") == incoming]
    assert hits, "500 的日志必须带上请求 ID"
    # 脱敏在 Formatter 出口做（record 保持原样），故校验渲染结果
    rendered = ReadableFormatter("%(message)s").format(hits[0])
    assert "13800138000" not in rendered
    assert incoming in rendered


def test_logs_carry_the_same_request_id_as_response(client: TestClient, monkeypatch) -> None:
    """同一次请求：访问日志里的 request_id 与响应头一致（可 grep 串联）。"""
    records, handler, level = _capture("app.access")
    monkeypatch.setattr(get_settings(), "slow_request_ms", 1)  # 阈值 1ms：任何请求都算慢
    try:
        resp = client.get(
            "/api/v1/health", headers={"X-Request-ID": "abcdef0123456789abcdef0123456789"}
        )
    finally:
        _release("app.access", handler, level)

    assert records, "应有访问日志"
    slow = [r for r in records if "慢请求" in r.getMessage()]
    assert slow, "阈值 1ms 时应记慢请求 warning"
    assert slow[0].request_id == "abcdef0123456789abcdef0123456789"
    assert slow[0].request_id == resp.headers["x-request-id"]
    assert slow[0].levelno == logging.WARNING


def test_streaming_responses_are_not_reported_slow(client: TestClient, monkeypatch) -> None:
    """SSE 流式响应天然持续数秒，不应被算作慢请求（否则淹没真正的过载信号）。"""
    records, handler, level = _capture("app.access")
    monkeypatch.setattr(get_settings(), "slow_request_ms", 1)
    try:
        with client.stream("POST", "/api/v1/ai/ask/stream", json={"question": "你好"}) as resp:
            is_stream = "text/event-stream" in resp.headers.get("content-type", "")
            resp.read()
    finally:
        _release("app.access", handler, level)
    slow = [r for r in records if "慢请求" in r.getMessage()]
    if is_stream:
        assert not slow, "流式响应不应记慢请求"


def test_slow_request_threshold_respected(client: TestClient, monkeypatch) -> None:
    """阈值调大后不再产生慢请求告警（避免每次请求都刷日志）。"""
    records, handler, level = _capture("app.access")
    monkeypatch.setattr(get_settings(), "slow_request_ms", 10**6)
    try:
        client.get("/api/v1/health")
    finally:
        _release("app.access", handler, level)
    assert not [r for r in records if "慢请求" in r.getMessage()]


def test_mask_sensitive_hides_phone_and_tokens() -> None:
    """手机号保留前 3 后 4；Bearer 令牌、key=value 凭据与长随机串替换为占位符。"""
    for sample in (
        "用户 13800138000 登录",
        "用户 +8613800138000 登录",
        "用户 138-0013-8000 登录",
        "用户 138 0013 8000 登录",
        "用户 １３８００１３８０００ 登录（全角）",
    ):
        masked = mask_sensitive(sample)
        assert "13800138000" not in masked.replace("-", "").replace(" ", "")
        assert "****" in masked, sample

    for secret in (
        "token=supersecrettoken1234",
        "access_token: abc123def456ghi789",
        "?token=abc123def456ghi789",
        "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.sig",
        "value 0123456789abcdef0123456789abcdef0123456789",
        "opaque Zm9vYmFyVGVzdFRva2VuMTIzNDU2Nzg5MEFCQ0RFRgAAA",
    ):
        masked = mask_sensitive(secret)
        assert "<token>" in masked, secret


def test_mask_sensitive_keeps_current_request_id() -> None:
    """当前请求 ID 本身是长十六进制，但不能被误当令牌抹掉（否则日志无法串联）。"""
    token = request_id_var.set("0123456789abcdef0123456789abcdef0123456789012345678901")
    try:
        masked = mask_sensitive(
            "请求 0123456789abcdef0123456789abcdef0123456789012345678901 失败",
            keep=(request_id_var.get(),),
        )
    finally:
        request_id_var.reset(token)
    assert "0123456789abcdef0123456789abcdef0123456789012345678901" in masked


def test_mask_sensitive_keeps_business_identifier() -> None:
    """32 位十六进制业务标识（如 family_id=token_hex(16)）不应被当成令牌抹掉。"""
    masked = mask_sensitive("已撤销家族全部会话：family=8f3d2c1b0a9e7d6c5b4a39281706f5e4 user_id=7")
    assert "8f3d2c1b0a9e7d6c5b4a39281706f5e4" in masked


def test_formatters_mask_message_and_exception() -> None:
    """JSON 与可读两种格式都在出口脱敏：msg 里的手机号、堆栈里的原始值。"""
    try:
        raise ValueError("绑定参数 receiver_phone=13800138000 token=supersecrettoken1234")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="app.demo",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="处理失败 mobile=%s",
        args=("13912345678",),
        exc_info=exc_info,
    )
    record.request_id = "-"

    payload = json.loads(JsonFormatter().format(record))
    assert "13800138000" not in payload["exc"]
    assert "supersecrettoken1234" not in payload["exc"]
    assert "13912345678" not in payload["msg"]
    assert "139****5678" in payload["msg"]

    readable = ReadableFormatter("%(message)s").format(record)
    assert "13800138000" not in readable
    assert "supersecrettoken1234" not in readable


def test_json_formatter_emits_single_line_with_meta() -> None:
    """生产 JSON：单行可解析，含 request_id 与请求元信息（method/path/status/duration_ms）。"""
    id_token = request_id_var.set("abc123def456abc123def456abc123de")
    meta_token = request_meta_var.set({"method": "GET", "path": "/api/v1/health"})
    try:
        record = logging.LogRecord(
            name="app.access",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="慢请求",
            args=(),
            exc_info=None,
        )
        record.request_id = request_id_var.get()
        text = JsonFormatter().format(record)
        payload = json.loads(text)
    finally:
        request_id_var.reset(id_token)
        request_meta_var.reset(meta_token)

    assert "\n" not in text, "JSON 必须是单行（采集友好）"
    assert payload["request_id"] == "abc123def456abc123def456abc123de"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/health"
    assert "ts" in payload


def test_json_formatter_masks_path_meta() -> None:
    """JSON 的 path 元信息也要脱敏（被扫路径里可能带手机号），request_id 保留原样。"""
    id_token = request_id_var.set("abc123def456abc123def456abc123de")
    meta_token = request_meta_var.set({"method": "GET", "path": "/api/v1/nope/13912345678"})
    try:
        record = logging.LogRecord(
            name="app.access",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="慢请求",
            args=(),
            exc_info=None,
        )
        record.request_id = request_id_var.get()
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(id_token)
        request_meta_var.reset(meta_token)

    assert "13912345678" not in json.dumps(payload, ensure_ascii=False)
    assert payload["path"] == "/api/v1/nope/139****5678"
    assert payload["request_id"] == "abc123def456abc123def456abc123de"


def test_setup_logging_uses_json_in_prod_and_readable_in_dev(monkeypatch) -> None:
    """ENV 决定格式：非 dev 走 JSON（采集友好），dev 走可读格式；两者都带上下文过滤器。"""
    settings = get_settings()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_uvicorn = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    try:
        monkeypatch.setattr(settings, "env", "prod")
        logging_module.setup_logging()
        assert isinstance(root.handlers[0].formatter, JsonFormatter)

        monkeypatch.setattr(settings, "env", "dev")
        logging_module.setup_logging()
        assert not isinstance(root.handlers[0].formatter, JsonFormatter)
        names = [type(f).__name__ for f in root.handlers[0].filters]
        assert "RequestContextFilter" in names
        # uvicorn 自带 handler 一律清掉并改为传播（dev/prod 都要，否则访问日志漏脱敏）
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            assert logging.getLogger(name).handlers == []
            assert logging.getLogger(name).propagate is True
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        for name, (handlers, propagate) in saved_uvicorn.items():
            logging.getLogger(name).handlers[:] = handlers
            logging.getLogger(name).propagate = propagate


def test_resolve_request_id_accepts_traceparent_style() -> None:
    """resolve_request_id 的边界：网关 hex / traceparent 风格可用，非法值生成新的。"""
    for ok in ("0123456789abcdef0123456789abcdef", "trace-4bf92f:12345678", "a.b-c_d:1"):
        assert resolve_request_id(ok) == ok
    for bad in (None, "", "abc", "有中文的请求id", "has space", "aaaaaaaa\n"):
        assert resolve_request_id(bad) != (bad or "")


def test_json_formatter_reads_meta_from_record() -> None:
    """元信息优先从 record 读：模拟异步 handler（QueueHandler）场景 contextvar 已还原。"""
    record = logging.LogRecord(
        name="app.access",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="慢请求",
        args=(),
        exc_info=None,
    )
    # 不设置任何 contextvar，只把字段放在 record 上（过滤器在正常路径下就是这么做的）
    record.request_id = "ffeeddccbbaa99887766554433221100"
    record.method = "GET"
    record.path = "/api/v1/shop/products"
    record.status = 200
    record.duration_ms = 640
    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "ffeeddccbbaa99887766554433221100"
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/shop/products"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 640


def test_cors_exposes_request_id(client: TestClient) -> None:
    """跨域前端要能读到 X-Request-ID（排障时把请求与后端日志对上）。"""
    resp = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    exposed = resp.headers.get("access-control-expose-headers", "")
    assert "X-Request-ID" in exposed or "x-request-id" in exposed.lower()
