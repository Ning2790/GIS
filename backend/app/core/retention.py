"""按时间列批量删除的通用助手（数据保留期清理用）。

只做「按条件 + 分批 + 单次上限」的删除，不含业务判断——每类数据删什么、
保留多久，由**各自模块的 service** 定义（跨模块只走 service）。

- **每批 commit**：大表一次删几十万行会持有长事务、膨胀 WAL 并阻塞写入；
- **单次上限**：超出留到下一次（任务每天跑，能持续收敛），保证任务时长可控；
- `count_expired` 供 dry-run 预估删除量（先看量再动手）。
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session


def cutoff_of(days: int) -> datetime:
    """N 天前的 UTC 时间点（保留期边界）。"""
    return datetime.now(UTC) - timedelta(days=days)


def batch_delete(
    db: Session,
    model: type,
    *,
    condition: ColumnElement[bool],
    batch_size: int,
    limit: int,
) -> int:
    """分批删除满足条件的行，返回删除总数（不超过 limit）。

    以主键子查询 + `delete in_` 的方式删，避免一次 `DELETE ... WHERE 时间` 走全表；
    每批提交，单批条数受 batch_size 控制。
    """
    total = 0
    while total < limit:
        size = min(batch_size, limit - total)
        ids = db.scalars(select(model.id).where(condition).order_by(model.id).limit(size)).all()
        if not ids:
            break
        db.execute(delete(model).where(model.id.in_(ids)))
        db.commit()
        total += len(ids)
    return total


def count_expired(db: Session, model: type, *, condition: ColumnElement[bool], limit: int) -> int:
    """统计满足条件的行数（截断到 limit，避免全表 count 拖慢 dry-run）。"""
    stmt = select(model.id).where(condition).limit(limit).subquery()
    return int(db.scalar(select(func.count()).select_from(stmt)) or 0)
