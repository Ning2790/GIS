"""files 业务逻辑层：受控上传与鉴权读取（P2，需求 4.1）。

- 上传：登录用户；类型 / 大小校验；对象键由服务端生成
  （``uploads/{user_id}/{uuid}{ext}``），不接受客户端路径（防穿越）；
  `public=True` 的公开文件仅限图片（商品图等展示内容，任何人可读）。
  **图片在上传时压缩并生成缩略图**（见 imageops）：列表页读缩略图、详情页读原图。
- 读取：公开文件任何人可读；私有文件仅上传者或管理员（未登录 401，
  其余按 404 处理，不泄漏存在性）；内容经本服务代理流出，不暴露对象存储直链。
  `variant=thumb` 读缩略图，无缩略图（非图片 / 存量文件）时回退原图。
- 对象存储未配置 / 不可用时返回 503（UnavailableError）；写入对象或入库 flush 失败会
  删除已上传对象（补偿）；仅**提交结果不确定**（如提交超时，可能服务端已提交）时保留
  对象并记 error 日志待对账——见 upload 注释。
"""

import logging
import uuid
from io import BytesIO
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import BadRequestError, NotFoundError, UnauthorizedError, UnavailableError
from app.core.input_guard import has_forbidden_chars
from app.modules.files import imageops, repository
from app.modules.files.models import FileObject
from app.modules.users.models import User, UserRole

if TYPE_CHECKING:
    from minio import Minio

logger = logging.getLogger(__name__)

VARIANT_ORIGINAL = "original"
VARIANT_THUMBNAIL = "thumb"

# 白名单类型 -> 扩展名（对象键只用这里的后缀，不信任原始文件名）
_EXTENSION_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

# 缩略图对象键后缀 -> Content-Type（服务端生成，键里的后缀是可信的）
_TYPE_BY_OBJECT_EXT = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

_client: "Minio | None" = None


def _get_client() -> "Minio | None":
    """MinIO 客户端（懒加载）。未配置 endpoint 时返回 None（上传 / 下载 503）。"""
    global _client
    settings = get_settings()
    if not settings.minio_endpoint:
        return None
    if _client is None:
        from minio import Minio

        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def _ensure_bucket(client: "Minio", bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)


def _discard(client: "Minio", bucket: str, *object_keys: str | None) -> None:
    """尽力删除对象（补偿路径）：清理失败不掩盖原始异常。"""
    for key in object_keys:
        if not key:
            continue
        try:
            client.remove_object(bucket, key)
        except Exception:  # noqa: BLE001 - 补偿失败只留下一次无效调用，不向上抛
            pass


def _validate(content_type: str, data: bytes) -> str:
    """校验类型与大小，返回对象键使用的扩展名。"""
    settings = get_settings()
    if content_type not in settings.file_allowed_types or content_type not in _EXTENSION_BY_TYPE:
        raise BadRequestError(f"不支持的文件类型：{content_type or '未知'}")
    if not data:
        raise BadRequestError("文件内容为空")
    max_bytes = settings.file_max_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise BadRequestError(f"文件超过大小上限（{settings.file_max_mb} MB）")
    return _EXTENSION_BY_TYPE[content_type]


def upload(
    db: Session,
    user: User,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    public: bool = False,
) -> FileObject:
    """上传文件（登录用户），返回元数据。

    public=True 表示公开可读（商品图等展示内容），仅图片类型可标记；
    默认私有（资质证明等敏感材料）。

    图片先压缩（长边 ≤ IMAGE_MAX_EDGE）并生成缩略图（长边 ≤ IMAGE_THUMBNAIL_EDGE）；
    压缩无收益（小图 / 已优化）或图片不可解码时原样入库，缩略图缺失时读取回退原图。
    """
    extension = _validate(content_type, data)
    if has_forbidden_chars(filename or ""):
        # multipart 文件名不走 JSON 中间件；NUL / 控制字符会让对象键与入库同时出问题
        raise BadRequestError("文件名包含非法字符")
    if public and not content_type.startswith("image/"):
        raise BadRequestError("只有图片可以设为公开")
    settings = get_settings()
    client = _get_client()
    if client is None:
        raise UnavailableError("文件存储未配置，暂时无法上传")

    processed = imageops.process(
        data,
        content_type,
        max_edge=settings.image_max_edge,
        jpeg_quality=settings.image_jpeg_quality,
        thumbnail_edge=settings.image_thumbnail_edge,
    )
    stored = processed.data if processed else data
    thumbnail = processed.thumbnail if processed else None

    object_key = f"uploads/{user.id}/{uuid.uuid4().hex}{extension}"
    thumbnail_key = None
    if thumbnail is not None:
        thumb_ext = imageops.extension_for(processed.thumbnail_content_type or "")
        thumbnail_key = f"{object_key.rsplit('.', 1)[0]}.thumb{thumb_ext}"

    bucket = settings.minio_bucket
    try:
        _ensure_bucket(client, bucket)
        client.put_object(
            bucket, object_key, BytesIO(stored), length=len(stored), content_type=content_type
        )
        if thumbnail is not None:
            client.put_object(
                bucket,
                thumbnail_key,
                BytesIO(thumbnail),
                length=len(thumbnail),
                content_type=processed.thumbnail_content_type,
            )
    except Exception as exc:  # 对象存储不可达：如实返回 503
        _discard(client, bucket, object_key, thumbnail_key)
        raise UnavailableError("文件存储暂不可用，请稍后再试") from exc

    record = FileObject(
        user_id=user.id,
        object_key=object_key,
        thumbnail_key=thumbnail_key,
        filename=(filename or "unnamed")[:255],
        content_type=content_type,
        size=len(stored),
        original_size=processed.original_size if processed else None,
        is_public=public,
    )
    try:
        # flush 阶段失败：肯定未提交，连同已写入的对象一起清掉
        repository.create(db, record)
    except Exception:
        db.rollback()
        _discard(client, bucket, object_key, thumbnail_key)
        raise
    try:
        db.commit()
    except Exception:
        db.rollback()
        # 提交失败的语义不确定（可能是「服务端已提交、客户端超时」）：**不删对象**。
        # 留下两个可对账清理的对象，好过让已入库的记录指向被删对象（列表页裂图）。
        logger.error(
            "文件入库提交失败，已保留对象待对账：object_key=%s thumbnail_key=%s",
            object_key,
            thumbnail_key,
        )
        raise
    return record


def get_readable(db: Session, file_id: int, user: User | None) -> FileObject:
    """返回可读的文件元数据。

    公开文件任何人可读；私有文件仅上传者 / 管理员（其余按不存在处理，不泄漏）；
    未登录访问私有文件按未认证处理（401）。
    """
    record = repository.get(db, file_id)
    if record is None:
        raise NotFoundError("文件不存在")
    if record.is_public:
        return record
    if user is None:
        raise UnauthorizedError()
    if record.user_id == user.id or user.role == UserRole.ADMIN:
        return record
    raise NotFoundError("文件不存在")


def require_owned(db: Session, file_id: int, user: User) -> FileObject:
    """平台引用校验（跨模块只走 service）：文件必须存在且属于该用户。

    供商户在商品上引用自己上传的图片（不能引用他人文件）。
    """
    record = repository.get(db, file_id)
    if record is None or record.user_id != user.id:
        raise NotFoundError("文件不存在")
    return record


def open_stream(
    db: Session, file_id: int, user: User | None, *, variant: str = VARIANT_ORIGINAL
) -> tuple[FileObject, Any, str]:
    """读取文件内容：返回 (元数据, 对象存储响应流, 实际 Content-Type)。

    variant=thumb 读缩略图，**两种缺失都回退原图**：没有缩略图（非图片 / 存量文件 /
    上传时不可解码）与缩略图对象丢失（人工清理、快照不一致）——列表页拿到比原图小
    几倍的图，比拿到裂图好。调用方负责 close/release_conn。
    """
    record = get_readable(db, file_id, user)
    settings = get_settings()
    client = _get_client()
    if client is None:
        raise UnavailableError("文件存储未配置")

    if variant == VARIANT_THUMBNAIL and record.thumbnail_key:
        try:
            response = client.get_object(settings.minio_bucket, record.thumbnail_key)
        except Exception:  # noqa: BLE001 - 缩略图取不到不是致命错误，回退原图
            logger.warning(
                "缩略图对象缺失，回退原图：file_id=%s key=%s", file_id, record.thumbnail_key
            )
        else:
            extension = record.thumbnail_key[record.thumbnail_key.rfind(".") :]
            return record, response, _TYPE_BY_OBJECT_EXT.get(extension, record.content_type)

    try:
        response = client.get_object(settings.minio_bucket, record.object_key)
    except Exception as exc:
        raise NotFoundError("文件内容不存在") from exc
    return record, response, record.content_type


def file_exists(db: Session, file_id: int) -> bool:
    """平台文件引用校验（供商户注册的 license_file 检查，跨模块只走 service）。"""
    return repository.get(db, file_id) is not None
