"""files 模块路由：受控上传与鉴权读取（P2，需求 4.1）。

- POST /files：登录用户上传（jpg / png / webp / pdf，≤ FILE_MAX_MB）；
  `public=true`（仅图片）表示公开可读，用于商品图等展示内容；
  **图片上传时压缩并生成缩略图**（长边上限见配置）；
- GET /files/{id}：公开文件任何人可读；私有文件仅上传者 / 管理员。
  `?variant=thumb` 读缩略图（列表页用），无缩略图时回退原图。
"""

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession, OptionalUser
from app.core.config import get_settings
from app.core.errors import BadRequestError
from app.core.response import ok
from app.modules.files import service
from app.modules.files.models import FileObject
from app.modules.files.schemas import FilePublic

router = APIRouter(prefix="/files", tags=["files"])


def _public(record: FileObject) -> FilePublic:
    url = f"/api/v1/files/{record.id}"
    # 只有真的生成了缩略图才给地址：动图 / 不可解码 / 超像素上限的图片没有缩略图，
    # 前端据此回退原图（不把「会把原图当缩略图下发」的地址报出去）
    thumbnail_url = f"{url}?variant=thumb" if record.thumbnail_key else None
    return FilePublic(
        id=record.id,
        filename=record.filename,
        content_type=record.content_type,
        size=record.size,
        original_size=record.original_size,
        is_public=record.is_public,
        url=url,
        thumbnail_url=thumbnail_url,
    )


@router.post("", summary="上传文件（登录用户，jpg/png/webp/pdf；图片可设公开）")
def upload(
    file: Annotated[UploadFile, File(description="文件，≤ 大小上限见配置")],
    db: DbSession,
    current_user: CurrentUser,
    public: Annotated[bool, Form(description="是否公开（仅图片可设；商品图等展示内容）")] = False,
) -> dict:
    # 只读"上限 + 1"字节：超限直接拒绝，避免把超大文件全读进内存
    max_bytes = get_settings().file_max_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise BadRequestError(f"文件超过大小上限（{get_settings().file_max_mb} MB）")
    record = service.upload(
        db,
        current_user,
        filename=file.filename or "unnamed",
        content_type=file.content_type or "",
        data=data,
        public=public,
    )
    return ok(_public(record).model_dump(mode="json"), msg="上传成功")


@router.get(
    "/{file_id}",
    summary="读取文件（公开文件任何人可读；私有仅本人 / 管理员；variant=thumb 读缩略图）",
)
def download(
    file_id: int,
    db: DbSession,
    current_user: OptionalUser,
    variant: Annotated[
        Literal["original", "thumb"], Query(description="thumb = 缩略图（列表页用）")
    ] = "original",
) -> StreamingResponse:
    record, response, content_type = service.open_stream(db, file_id, current_user, variant=variant)

    def _iter_chunks():
        try:
            yield from response.stream(64 * 1024)
        finally:
            response.close()
            response.release_conn()

    headers = {
        # RFC 5987：中文文件名安全放入头部
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(record.filename)}",
        # 公开图片（商品图）可缓存：列表页缩略图重复加载不打到对象存储
        "Cache-Control": "public, max-age=3600" if record.is_public else "private, max-age=60",
    }
    return StreamingResponse(_iter_chunks(), media_type=content_type, headers=headers)
