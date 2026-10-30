"""输入防护测试：NUL / C0 控制字符 / 超 int32 路径 ID 在路由前返回 422，正常请求不受影响。"""

from fastapi.testclient import TestClient

from app.core.input_guard import has_forbidden_chars, payload_has_forbidden_chars


def test_forbidden_char_detection() -> None:
    assert has_forbidden_chars("\x00")
    assert has_forbidden_chars("a\x08b")
    assert has_forbidden_chars("\x7f")
    # 换行 / 制表符是合法文本内容（多行描述、地址）
    assert not has_forbidden_chars("a\tb\nc\r")
    assert payload_has_forbidden_chars({"a": ["ok", {"b": "x\x00y"}]})
    assert not payload_has_forbidden_chars({"a": ["ok", {"b": "正常文本"}]})


def test_query_nul_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/shop/products", params={"keyword": "青海\x00湖"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 40000 and "非法字符" in body["msg"]


def test_query_control_char_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/travel/attractions", params={"city": "西宁\x08"})
    assert resp.status_code == 422


def test_path_int32_overflow_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/travel/attractions/2147483648")
    assert resp.status_code == 422
    assert "编号" in resp.json()["msg"]
    # 边界内仍按“资源不存在”处理，而不是 422
    assert client.get("/api/v1/travel/attractions/2147483647").status_code == 404


def test_path_nul_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/travel/attractions/%00")
    assert resp.status_code == 422


def test_json_body_nul_rejected(client: TestClient) -> None:
    # \u0000 在 JSON 里是转义，解析后才是 NUL——验证中间件是解析后检查
    resp = client.post(
        "/api/v1/auth/login",
        json={"phone": "1380000\u0000000", "password": "secret123"},
    )
    assert resp.status_code == 422
    assert "请求体" in resp.json()["msg"]


def test_normal_json_body_still_reaches_app(client: TestClient) -> None:
    """缓冲并重放请求体后，正常 JSON 请求仍能被业务层解析。"""
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13900000000", "password": "wrong-pass"}
    )
    # 业务层正常处理（账号不存在 / 密码错误），不是中间件拦截
    assert resp.status_code in (400, 401)
    assert resp.json()["code"] != 40000 or "非法字符" not in resp.json().get("msg", "")
