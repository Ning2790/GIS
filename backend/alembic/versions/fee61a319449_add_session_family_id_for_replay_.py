"""add session family id for replay detection

Revision ID: fee61a319449
Revises: 1b1aa814d3ab
Create Date: 2026-10-13 20:02:01.962253

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = 'fee61a319449'
down_revision: str | None = '1b1aa814d3ab'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 三步骤：先加可空列 → 回填（历史会话各自成族）→ 收紧为 NOT NULL。
    # 非空表上直接加 NOT NULL 列会报 NotNullViolation（autogenerate 的已知盲区）。
    op.add_column('sessions', sa.Column('family_id', sa.String(length=32), nullable=True))
    op.execute("UPDATE sessions SET family_id = 'legacy-' || id WHERE family_id IS NULL")
    op.alter_column('sessions', 'family_id', nullable=False)
    op.create_index(op.f('ix_sessions_family_id'), 'sessions', ['family_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sessions_family_id'), table_name='sessions')
    op.drop_column('sessions', 'family_id')
