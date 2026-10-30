"""公共层分页助手测试。"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.pagination import PageParams, PageQuery, page_data, paginate
from app.db.session import SessionLocal
from app.modules.users import service as users_service
from app.modules.users.models import User


def test_page_data_shape() -> None:
    page = PageQuery(page=2, page_size=10)
    assert page_data([{"id": 1}], total=11, page=page) == {
        "items": [{"id": 1}],
        "total": 11,
        "page": 2,
        "page_size": 10,
    }


def test_page_params_bind_as_query_parameters() -> None:
    """PageParams 在真实路由上装配查询参数：有默认值，越界由框架返回 422。"""
    probe_app = FastAPI()

    @probe_app.get("/probe")
    def probe(page: PageParams) -> dict:
        return {"page": page.page, "page_size": page.page_size}

    client = TestClient(probe_app)
    assert client.get("/probe").json() == {"page": 1, "page_size": 20}
    assert client.get("/probe?page=2&page_size=50").json() == {"page": 2, "page_size": 50}
    assert client.get("/probe?page=0").status_code == 422
    assert client.get("/probe?page_size=101").status_code == 422


def test_paginate_limits_rows_and_counts_filtered_total() -> None:
    """limit/offset 正确切片；total 是过滤后的总数（用手机号前缀隔离数据）。"""
    with SessionLocal() as db:
        for i in range(3):
            users_service.register(db, phone=f"1390000{i:04d}", password="pass123456")
        stmt = select(User).where(User.phone.like("1390000%")).order_by(User.id)

        rows, total = paginate(db, stmt, PageQuery(page=1, page_size=2))
        assert total == 3
        assert len(rows) == 2

        rows, total = paginate(db, stmt, PageQuery(page=2, page_size=2))
        assert total == 3
        assert [row.phone for row in rows] == ["13900000002"]

        rows, _ = paginate(db, stmt, PageQuery(page=9, page_size=20))
        assert rows == []
