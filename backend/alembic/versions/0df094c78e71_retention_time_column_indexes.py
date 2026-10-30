"""retention time column indexes

Revision ID: 0df094c78e71
Revises: c3ef3706c938
Create Date: 2026-10-17 14:40:34.772812

数据保留期清理（数据增长方案 P1）需要按时间列删除，时间列必须有索引，
否则大表上的 DELETE 会退化为全表扫描（锁等待 + IO 尖峰）。
迁移期不想锁表 → PostgreSQL 用 `CREATE INDEX CONCURRENTLY`（alembic 需在
autocommit_block 里执行，因为 CONCURRENTLY 不能进事务）；SQLite 走普通建索引。
"""
from collections.abc import Sequence

from alembic import op

revision: str = '0df094c78e71'
down_revision: str | None = 'c3ef3706c938'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (索引名, 表名, 列名)
_INDEXES = (
    ('ix_ai_messages_created_at', 'ai_messages', 'created_at'),
    ('ix_cs_messages_created_at', 'cs_messages', 'created_at'),
    ('ix_device_bindings_last_seen_at', 'device_bindings', 'last_seen_at'),
    ('ix_inventory_created_at', 'inventory', 'created_at'),
    ('ix_orders_created_at', 'orders', 'created_at'),
)


def upgrade() -> None:
    # CONCURRENTLY 不能进事务：PG 在 autocommit 块里建（不阻塞写入）；
    # SQLite 不支持 CONCURRENTLY，autocommit 块对其无副作用、普通建索引即可。
    with op.get_context().autocommit_block():
        for name, table, column in _INDEXES:
            op.create_index(name, table, [column], unique=False, postgresql_concurrently=True)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, _column in reversed(_INDEXES):
            op.drop_index(name, table_name=table, postgresql_concurrently=True)
