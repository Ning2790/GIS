"""files 数据访问层。

仅供本模块 service 调用，禁止被其他模块 import。
本层只 flush 不 commit：事务边界由 service 统一控制。
"""

from sqlalchemy.orm import Session

from app.modules.files.models import FileObject


def create(db: Session, file: FileObject) -> FileObject:
    db.add(file)
    db.flush()
    db.refresh(file)
    return file


def get(db: Session, file_id: int) -> FileObject | None:
    return db.get(FileObject, file_id)
