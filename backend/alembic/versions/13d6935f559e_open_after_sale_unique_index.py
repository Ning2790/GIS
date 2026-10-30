"""open after sale unique index

Revision ID: 13d6935f559e
Revises: beef25506c55
Create Date: 2026-10-15 19:06:08.174488

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = '13d6935f559e'
down_revision: str | None = 'beef25506c55'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 防御性收敛：并发双开（旧代码的 TOCTOU）可能已留下同订单多条未结单，
    # 会让下面的唯一索引建不上。保留最新一条为未结单，其余标记为已撤销。
    op.execute(
        "UPDATE after_sales SET status = 'withdrawn', "
        "closed_at = COALESCE(closed_at, updated_at) "
        "WHERE status IN ('pending', 'processing') AND id NOT IN ("
        "  SELECT MAX(id) FROM after_sales WHERE status IN ('pending', 'processing') "
        "  GROUP BY order_id"
        ")"
    )
    # 「同一订单同时只允许一条未结单」由数据库兜底（PG / SQLite 都支持部分唯一索引）
    op.create_index(
        'uq_after_sales_open_order',
        'after_sales',
        ['order_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
        sqlite_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index('uq_after_sales_open_order', table_name='after_sales')
