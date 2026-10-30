"""add postgis geom to attractions

给 attractions 增加 PostGIS 几何列（map 卡）：
- 手工迁移：geom 不映射到 ORM（只由迁移维护），autogenerate 对比时在 env.py 里排除；
- 回填既有数据的经纬度；GIST 索引支撑 bbox 点位查询（&& ST_MakeEnvelope）。
新增景点需同步 geom：见 app/modules/travel/repository.py 的 backfill_geom（seed 脚本已调用）。
- SQLite（默认开发库 / 测试）没有几何类型与 ST_* 函数：本迁移按方言门控跳过，
  点位查询在 SQLite 下退化为经纬度过滤（见 travel 模块 repository）。

Revision ID: 22b8631170c5
Revises: 24c4e9b5b600
Create Date: 2026-10-13 13:53:00.013215

"""
from collections.abc import Sequence

from alembic import op

revision: str = '22b8631170c5'
down_revision: str | None = '24c4e9b5b600'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE attractions ADD COLUMN geom geometry(Point, 4326)")
    op.execute(
        "UPDATE attractions SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) "
        "WHERE longitude IS NOT NULL AND latitude IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_attractions_geom ON attractions USING GIST (geom)")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_attractions_geom")
    op.execute("ALTER TABLE attractions DROP COLUMN IF EXISTS geom")
