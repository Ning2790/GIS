"""排队闸门 e2e（真 HTTP）：503「排队中」、计数释放、交易优先。

闸门计数在进程内，与测试进程里的 uvicorn 共享——直接操纵计数即可稳定
构造"满载"场景（比压真实并发更确定）。
"""

import time

import httpx
import pytest

from app.core import queue_gate
from app.core.config import get_settings
from tests_e2e.helpers import RECEIVER


@pytest.fixture(autouse=True)
def _reset_gate() -> None:
    """每个用例前等计数归零再清零。

    客户端读到响应时，服务端中间件的 finally 释放可能还差几微秒——
    上一个用例的残留会让"容量=1"的断言偶发失败。
    """
    deadline = time.time() + 1.0
    while time.time() < deadline and sum(queue_gate._inflight.values()) > 0:
        time.sleep(0.02)
    queue_gate._inflight.clear()
    yield
    queue_gate._inflight.clear()


def test_view_gate_503_and_release(api: httpx.Client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "queue_max_view", 1)
    # 人为占满（失败时打印残留计数，便于定位泄漏来源）
    assert queue_gate.acquire("view"), dict(queue_gate._inflight)
    try:
        resp = api.get("/travel/attractions", params={"page": 1, "page_size": 1})
        assert resp.status_code == 503, resp.text
        assert resp.json()["code"] == 50300
        assert resp.headers["Retry-After"] == "1"
    finally:
        queue_gate.release("view")
    # 释放后恢复放行；计数归零（服务端 finally 释放晚于客户端收到响应，轮询等待）
    assert api.get("/travel/attractions", params={"page": 1, "page_size": 1}).status_code == 200
    deadline = time.time() + 1.0
    while time.time() < deadline and queue_gate._inflight["view"] != 0:
        time.sleep(0.02)
    assert queue_gate._inflight["view"] == 0, dict(queue_gate._inflight)


def test_trade_priority_over_view(api: httpx.Client, monkeypatch) -> None:
    """查看类满载时，交易请求仍进入路由（优先保障交易）。"""
    monkeypatch.setattr(get_settings(), "queue_max_view", 1)
    assert queue_gate.acquire("view")
    try:
        resp = api.post("/shop/orders", json={"product_id": 1, "quantity": 1, **RECEIVER})
        assert resp.status_code == 401  # 未认证（进入路由），而非 503（被闸门拦）
    finally:
        queue_gate.release("view")
