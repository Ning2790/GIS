"""生产加固（S10）：非 dev 关闭交互式文档 + 应用层安全响应头。"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


def test_docs_disabled_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "env", "prod")
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # 业务接口不受影响，且带安全响应头
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["strict-transport-security"] == "max-age=31536000"


def test_dev_keeps_docs_and_no_extra_headers() -> None:
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert "x-frame-options" not in resp.headers
