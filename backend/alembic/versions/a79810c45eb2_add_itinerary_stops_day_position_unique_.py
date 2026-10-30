"""add itinerary stops day position unique constraint

Revision ID: a79810c45eb2
Revises: 379cf47d841c
Create Date: 2026-10-13 15:01:12.495871

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = 'a79810c45eb2'
down_revision: str | None = '379cf47d841c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 唯一约束经由 ALTER TABLE 添加，SQLite 不支持 ALTER 约束：默认开发库跳过
    # （测试库由 create_all 建出该约束，PostgreSQL 行为不变）。
    if op.get_bind().dialect.name != "postgresql":
        return
    op.create_unique_constraint(
        'uq_itinerary_stop_day_pos', 'itinerary_stops', ['itinerary_id', 'day', 'position']
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_constraint('uq_itinerary_stop_day_pos', 'itinerary_stops', type_='unique')
