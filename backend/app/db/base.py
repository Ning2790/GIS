"""SQLAlchemy 声明基类。

所有模块的 ORM 模型都必须继承 Base。新增模型后记得在 app/db/models_registry.py
登记，否则 Alembic 自动生成迁移时检测不到新表。
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
