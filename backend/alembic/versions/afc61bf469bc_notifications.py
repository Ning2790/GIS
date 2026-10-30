"""notifications

Revision ID: afc61bf469bc
Revises: 0df094c78e71
Create Date: 2026-10-17 17:29:41.865520

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "afc61bf469bc"
down_revision: str | None = "0df094c78e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=64), nullable=False),
        sa.Column("content", sa.String(length=255), nullable=False),
        sa.Column("ref_type", sa.String(length=32), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # 列表（user_id + id 降序）与未读计数（user_id + is_read）各一条复合索引；
    # created_at 单列索引留给保留期清理。is_read 单列选择性太低，不单独建。
    op.create_index("ix_notifications_user_id_id", "notifications", ["user_id", "id"], unique=False)
    op.create_index(
        "ix_notifications_user_unread", "notifications", ["user_id", "is_read"], unique=False
    )
    op.create_index(
        op.f("ix_notifications_created_at"), "notifications", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notifications_created_at"), table_name="notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_id_id", table_name="notifications")
    op.drop_table("notifications")
