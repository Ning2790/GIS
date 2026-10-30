"""files ORM 模型：上传文件的元数据（内容存 MinIO，不入库）。"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FileObject(Base):
    """上传文件元数据。

    object_key 为对象存储中的键（服务端生成，不接受客户端路径）；
    读取权限由 is_public、user_id（上传者）与管理员角色共同决定（见 service）：
    公开文件（仅图片可标记）任何人可读，私有文件仅上传者 / 管理员。

    thumbnail_key 为上传时生成的缩略图对象键（列表页用）；None 表示无缩略图
    （非图片、存量文件或图片不可解码），读取 `?variant=thumb` 时回退原图。
    """

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    object_key: Mapped[str] = mapped_column(String(255), unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255), default=None)
    filename: Mapped[str] = mapped_column(String(255))  # 原始文件名（仅展示）
    content_type: Mapped[str] = mapped_column(String(64))
    # 入库对象字节数（图片压缩后为实际存入的大小）
    size: Mapped[int] = mapped_column(Integer)
    # 上传原始字节数：图片被压缩过时用于展示「原始 X → 存入 Y」；非图片为 None
    original_size: Mapped[int | None] = mapped_column(Integer, default=None)
    # 公开文件：任何人可读，用于商品图等展示性内容；默认私有（资质证明等）
    is_public: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
