"""Alembic 迁移环境。

连接串统一从 app.core.config 读取，避免在 alembic.ini 与 .env 里各写一份。

PostGIS 镜像会把 tiger / topology 两个系统 schema 放进数据库 search_path，
下面用「SET search_path TO public + include_name / include_object 过滤」把这批
系统对象排除在迁移对比之外。**不要删掉这些过滤**：去掉后 autogenerate 会生成
几十条 drop_table 去删 PostGIS 系统表（spatial_ref_sys / tiger / topology）。
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.db.models_registry  # noqa: F401  注册所有模型，供自动生成迁移使用
from alembic import context
from app.core.config import get_settings
from app.db.base import Base

config = context.config
# ConfigParser 会做 % 插值：数据库密码里含 % 时（URL 编码的 @ / # 很常见）必须转义。
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# PostGIS 系统对象：不参与迁移对比，也不允许生成删除语句。
SYSTEM_SCHEMAS = {"tiger", "topology", "information_schema", "pg_catalog"}
SYSTEM_TABLES = {"spatial_ref_sys"}


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """schema / 表名维度的过滤（与 include_object 配合使用）。"""
    if type_ == "schema":
        return name not in SYSTEM_SCHEMAS
    if type_ == "table":
        return name not in SYSTEM_TABLES
    return True


def include_object(
    object_: object,
    name: str,
    type_: str,
    reflected: bool,
    compare_to: object | None,
) -> bool:
    """对象维度过滤：跳过 PostGIS 系统 schema 与系统表。"""
    if type_ == "table":
        schema = getattr(object_, "schema", None)
        if schema in SYSTEM_SCHEMAS or name in SYSTEM_TABLES:
            return False
    if (
        type_ == "column"
        and name == "geom"
        and getattr(getattr(object_, "table", None), "name", None) == "attractions"
    ):
        # attractions.geom 是 PostGIS 专用列（map 卡）：不映射到 ORM、由迁移维护，
        # 对比时排除，避免被当成"模型里没有的列"生成 DROP。
        return False
    if type_ == "index" and name == "ix_attractions_geom":
        # 与上面配套：geom 的 GIST 索引也由迁移维护。
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # 隔离 search_path：否则 tiger / topology 系统表会混入默认 schema 的对比。
        # SET 是 PG 专有语法，仅在 PostgreSQL 上执行（默认开发库 SQLite 不需要）。
        # SET 是会话级、不受事务边界影响；随后的 commit() 是为了结束 SQLAlchemy 的
        # 隐式事务——若 configure 时连接处于事务中，Alembic 会判定事务由外部管理
        # （_in_external_transaction），migrate 后不做提交，事务会被静默回滚。
        if connection.dialect.name == "postgresql":
            connection.exec_driver_sql("SET search_path TO public")
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_name=include_name,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
