"""热点缓存 e2e（真 Redis）：命中行为、写路径自动失效。"""

import uuid

import httpx
from sqlalchemy import text

from tests_e2e.helpers import create_product, login, register_merchant


def test_product_list_cached_until_bump(api: httpx.Client, db) -> None:
    """列表响应被缓存：绕过写路径直改数据库不改变响应；bump 后立即更新。"""
    from app.core import cache

    merchant = register_merchant(api, db)
    mh = login(api, merchant)
    product = create_product(api, mh, stock=10)

    def list_names() -> list[str]:
        resp = api.get("/shop/products", params={"page": 1, "page_size": 50})
        assert resp.status_code == 200
        return [item["name"] for item in resp.json()["data"]["items"]]

    assert product["name"] in list_names()

    # 绕过写路径直改数据库：缓存未失效，响应仍是旧名（证明走了缓存）
    renamed = f"e2e-改名-{uuid.uuid4().hex[:6]}"
    with db() as session:
        session.execute(
            text("UPDATE products SET name = :n WHERE id = :i"),
            {"n": renamed, "i": product["id"]},
        )
        session.commit()
    names2 = list_names()
    assert renamed not in names2
    assert product["name"] in names2  # 旧值仍从缓存返回

    # bump 后立即看到新名字
    cache.bump_version("shop:products")
    assert renamed in list_names()


def test_new_product_visible_immediately(api: httpx.Client, db) -> None:
    """上架走写路径：缓存随之失效，新商品立即可见（不吃陈旧列表）。"""
    merchant = register_merchant(api, db)
    mh = login(api, merchant)
    api.get("/shop/products", params={"page": 1, "page_size": 50})  # 预热缓存
    product = create_product(api, mh, stock=5)
    resp = api.get("/shop/products", params={"page": 1, "page_size": 50})
    assert product["name"] in [item["name"] for item in resp.json()["data"]["items"]]
