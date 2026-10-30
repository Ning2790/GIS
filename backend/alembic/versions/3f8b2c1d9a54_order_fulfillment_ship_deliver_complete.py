"""order fulfillment ship deliver complete

Revision ID: 3f8b2c1d9a54
Revises: 77d9acc28672
Create Date: 2026-10-15 00:20:00.000000

履约（N3）：发货 / 签收 / 完成时间，全部可空（历史订单没有这些信息）。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '3f8b2c1d9a54'
down_revision: str | None = '77d9acc28672'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ### commands hand written (autogenerate 需要连库，本机 Docker 停用期间手写) ###
    op.add_column('orders', sa.Column('shipped_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('carrier', sa.String(length=32), nullable=True))
    op.add_column('orders', sa.Column('tracking_no', sa.String(length=64), nullable=True))
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands hand written ###
    op.drop_column('orders', 'completed_at')
    op.drop_column('orders', 'delivered_at')
    op.drop_column('orders', 'tracking_no')
    op.drop_column('orders', 'carrier')
    op.drop_column('orders', 'shipped_at')
    # ### end Alembic commands ###
