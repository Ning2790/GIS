"""users 模块：用户列表（管理员）与角色 / 状态扩展测试。"""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.modules.users.models import User, UserRole, UserStatus

ADMIN_PHONE = "13700000000"
ADMIN_PASSWORD = "admin123456"


def _ensure_admin(phone: str = ADMIN_PHONE) -> None:
    """直接落库创建管理员账号（管理员不经注册接口产生，生产环境由 seed 脚本创建）。"""
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.phone == phone)) is None:
            db.add(
                User(
                    phone=phone,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role=UserRole.ADMIN,
                    status=UserStatus.ACTIVE,
                    nickname="测试管理员",
                )
            )
            db.commit()


def _login(client: TestClient, phone: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"phone": phone, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _admin_headers(client: TestClient) -> dict[str, str]:
    _ensure_admin()
    return {"Authorization": f"Bearer {_login(client, ADMIN_PHONE, ADMIN_PASSWORD)}"}


def test_users_list_requires_token(client: TestClient) -> None:
    resp = client.get("/api/v1/users")
    assert resp.status_code == 401
    assert resp.json()["code"] == 40100


def test_users_list_forbidden_for_tourist(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register/tourist",
        json={"phone": "13710000001", "password": "pass123456"},
    )
    token = _login(client, "13710000001", "pass123456")
    resp = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json()["code"] == 40300


def test_users_list_pagination_and_filters(client: TestClient) -> None:
    headers = _admin_headers(client)
    # 造数据：两个待审核商户 / 企业 + 一个游客
    client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": "13720000001",
            "password": "pass123456",
            "license_no": "91370000AAAA0001",
            "role": "merchant",
        },
    )
    client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": "13720000002",
            "password": "pass123456",
            "license_no": "91370000AAAA0002",
            "role": "enterprise",
        },
    )
    client.post(
        "/api/v1/auth/register/tourist",
        json={"phone": "13720000003", "password": "pass123456", "nickname": "测试游客"},
    )

    # 分页形状与管理视图字段
    body = client.get("/api/v1/users?page=1&page_size=2", headers=headers).json()
    assert body["code"] == 0
    data = body["data"]
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2
    assert data["total"] >= 3
    assert set(data["items"][0]) >= {
        "id",
        "phone",
        "role",
        "status",
        "nickname",
        "license_no",
        "license_file",
        "created_at",
    }

    # 按状态过滤
    resp = client.get("/api/v1/users?status=pending_review", headers=headers)
    items = resp.json()["data"]["items"]
    assert items
    assert all(item["status"] == UserStatus.PENDING_REVIEW for item in items)

    # 按角色 + 关键词过滤（手机号全局唯一，结果确定）
    resp = client.get("/api/v1/users?role=merchant&keyword=13720000001", headers=headers)
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["items"][0]["phone"] == "13720000001"
    assert data["items"][0]["license_file"] is None

    # 分页切片：第 2 页
    resp = client.get("/api/v1/users?status=pending_review&page=2&page_size=1", headers=headers)
    data = resp.json()["data"]
    assert data["page"] == 2
    assert len(data["items"]) == 1

    # 越界参数由框架校验拦截
    assert client.get("/api/v1/users?page=0", headers=headers).status_code == 422
    assert client.get("/api/v1/users?page_size=101", headers=headers).status_code == 422


def test_rejected_user_cannot_login(client: TestClient) -> None:
    """资质被驳回（rejected）的账号不可登录。"""
    with SessionLocal() as db:
        db.add(
            User(
                phone="13730000001",
                password_hash=hash_password("pass123456"),
                role=UserRole.MERCHANT,
                status=UserStatus.REJECTED,
                nickname="被驳回商户",
            )
        )
        db.commit()
    resp = client.post(
        "/api/v1/auth/login", json={"phone": "13730000001", "password": "pass123456"}
    )
    assert resp.status_code == 401
    assert "审核未通过" in resp.json()["msg"]
