"""基础接口测试：服务信息与健康检查。"""

from fastapi.testclient import TestClient


def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["app"]


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["status"] == "healthy"


def test_no_module_stubs_remain(client):
    """所有业务模块均已实现，占位路由应全部下线。"""
    for module in ("travel", "map", "gear", "shop", "b2b", "ai", "cs", "admin"):
        resp = client.get(f"/api/v1/{module}/_status")
        assert resp.status_code == 404, module


def test_not_found_returns_envelope(client):
    """未知路由也返回统一信封（此前是 Starlette 的 {"detail": "Not Found"}）。"""
    resp = client.get("/api/v1/definitely-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 40400
    assert body["msg"] == "资源不存在"


def test_unhandled_exception_returns_envelope():
    """未捕获异常兜底为 500 信封（不泄露堆栈）。"""
    from app.main import create_app

    probe_app = create_app()

    @probe_app.get("/boom")
    def _boom() -> dict:
        raise RuntimeError("boom")

    client = TestClient(probe_app, raise_server_exceptions=False)
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 50000
    assert body["msg"] == "服务内部错误"
