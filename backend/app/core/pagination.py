"""统一分页。

列表接口一律用这里的形状，不要在模块里各写一套：
- 请求参数：PageParams（page 从 1 开始；page_size 默认 20，上限 100）；
- 成功响应的 data：{items, total, page, page_size}。

PageParams 是依赖别名（写法同 app/api/deps.py 的 DbSession / CurrentUser），
路由里直接声明 `page: PageParams`，不要写 `= Query(...)` 形式的默认值。

用法（路由里统一三步：service 取数 → schema 序列化 → page_data 组装）：

    @router.get("/things", summary="列表")
    def list_things(db: DbSession, page: PageParams) -> dict:
        rows, total = service.list_things(db, page)
        items = [ThingPublic.model_validate(row).model_dump(mode="json") for row in rows]
        return ok(page_data(items, total, page))
"""

from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PageQuery:
    """分页参数（由 PageParams 依赖从查询参数装配）。"""

    page: int
    page_size: int


def _page_params(
    page: Annotated[int, Query(ge=1, description="页码，从 1 开始")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数，最大 100")] = 20,
) -> PageQuery:
    """FastAPI 依赖：把查询参数 page / page_size 装配成 PageQuery。

    边界（ge / le）定义在查询参数上，越界由框架统一返回 422。
    """
    return PageQuery(page=page, page_size=page_size)


# 路由里直接声明 `page: PageParams`。
PageParams = Annotated[PageQuery, Depends(_page_params)]


def paginate(db: Session, stmt: Select[Any], page: PageQuery) -> tuple[list[Any], int]:
    """执行分页查询，返回 (当页行, 总数)。

    stmt 为未加 limit / offset 的查询，排序由调用方指定；
    total 统计 stmt 过滤条件下的全量行数（不受分页切片影响）。
    """
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.limit(page.page_size).offset((page.page - 1) * page.page_size)).all()
    return list(rows), int(total)


def page_data(items: list[Any], total: int, page: PageQuery) -> dict[str, Any]:
    """组装统一分页 data 形状；items 应为已序列化的响应模型字典。"""
    return {"items": items, "total": total, "page": page.page, "page_size": page.page_size}
