"""tests_e2e 的 HTTP / 数据库助手。"""

import threading
import uuid

import httpx
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

PASSWORD = "E2e123456"


def unique_phone() -> str:
    return "139" + uuid.uuid4().hex[:8]


def register_tourist(api: httpx.Client, phone: str | None = None) -> str:
    phone = phone or unique_phone()
    resp = api.post("/auth/register/tourist", json={"phone": phone, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return phone


def register_merchant(api: httpx.Client, db: sessionmaker, role: str = "merchant") -> str:
    """注册商户 / 企业并直接激活（资质审核流程不是并发测试的验证目标）。"""
    phone = unique_phone()
    resp = api.post(
        "/auth/register/enterprise",
        json={
            "phone": phone,
            "password": PASSWORD,
            "role": role,
            "license_no": f"E2E-{uuid.uuid4().hex[:8]}",
        },
    )
    assert resp.status_code == 200, resp.text
    with db() as session:
        session.execute(
            text("UPDATE users SET status = 'active' WHERE phone = :phone"), {"phone": phone}
        )
        session.commit()
    return phone


def login(api: httpx.Client, phone: str) -> dict[str, str]:
    resp = api.post("/auth/login", json={"phone": phone, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}


def user_id_of(db: sessionmaker, phone: str) -> int:
    with db() as session:
        return int(
            session.execute(
                text("SELECT id FROM users WHERE phone = :p"), {"p": phone}
            ).scalar_one()
        )


def create_product(
    api: httpx.Client, merchant_headers: dict[str, str], *, stock: int, price: float = 1.0
) -> dict:
    resp = api.post(
        "/shop/products",
        headers=merchant_headers,
        json={"name": f"e2e-并发商品-{uuid.uuid4().hex[:6]}", "price": price, "stock": stock},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def run_concurrently(fn, n: int) -> list:
    """让 n 个线程在 barrier 处同步后并发执行 fn(index)，按索引返回结果。

    线程内异常以异常对象形式返回（由调用方断言时暴露）。
    """
    results: list = [None] * n
    barrier = threading.Barrier(n)

    def worker(index: int) -> None:
        barrier.wait()
        try:
            results[index] = fn(index)
        except Exception as exc:  # noqa: BLE001
            results[index] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return results


# 下单必填的收货信息（订单测试用固定值）
RECEIVER = {
    "receiver_name": "测试收货人",
    "receiver_phone": "13800000000",
    "receiver_address": "青海省西宁市城西区测试路 1 号",
}
