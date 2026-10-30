"""unique default address index

并发兜底（评审发现）：同一用户可并发「设默认」或在空地址簿上并发新增，
服务层的「清旧默认 → 置新默认」会出现写偏斜留下两个默认地址。
加一条部分唯一索引在数据库层收口：每用户至多一行 is_default = true。

Revision ID: 5c7d9e1f2a3b
Revises: 3f8b2c1d9a54
Create Date: 2026-10-15 09:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '5c7d9e1f2a3b'
down_revision: str | None = '3f8b2c1d9a54'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 历史数据里可能已存在同一用户多个默认（旧代码并发写入的产物）：先收敛为 id 最小的那条
    op.execute(
        "UPDATE user_addresses SET is_default = false "
        "WHERE is_default AND id NOT IN ("
        "  SELECT MIN(id) FROM user_addresses WHERE is_default GROUP BY user_id"
        ")"
    )
    # 部分唯一索引：PG 与 SQLite 均支持（WHERE is_default）
    op.create_index(
        'uq_user_addresses_default',
        'user_addresses',
        ['user_id'],
        unique=True,
        postgresql_where=sa.text('is_default'),
        sqlite_where=sa.text('is_default'),
    )


def downgrade() -> None:
    op.drop_index('uq_user_addresses_default', table_name='user_addresses')
