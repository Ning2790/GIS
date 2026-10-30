"""为存量图片补缩略图（一次性运维脚本，图片增强之后）。

用法（backend 目录）：
    uv run python scripts/make_thumbnails.py            # 补缩略图
    uv run python scripts/make_thumbnails.py --dry-run  # 只盘点，不写对象存储

- 只处理 files 表中图片类型、且 thumbnail_key 为空的行；幂等，可反复运行。
- 内容不可解码（伪造头 / 损坏）跳过计数——与上传同策略，不阻断整批。
- **不改动原图对象**：原图只在"上传当时"压缩，避免同一个 URL 内容突变、
  与浏览器 / CDN 已缓存的副本不一致。这里只生成缺失的缩略图。
"""

import argparse
import sys
from io import BytesIO
from pathlib import Path

from minio import Minio
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.errors import UnavailableError  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.files import imageops  # noqa: E402
from app.modules.files.models import FileObject  # noqa: E402


def _client() -> Minio:
    settings = get_settings()
    if not settings.minio_endpoint:
        raise UnavailableError("未配置 MinIO（MINIO_ENDPOINT），无法补缩略图")
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="为存量图片补缩略图")
    parser.add_argument("--dry-run", action="store_true", help="只盘点不写入")
    args = parser.parse_args()

    settings = get_settings()
    client = _client()
    bucket = settings.minio_bucket

    done = skipped_type = undecodable = failed = 0
    with SessionLocal() as db:
        rows = db.scalars(
            select(FileObject).where(
                FileObject.content_type.in_(tuple(imageops.IMAGE_CONTENT_TYPES)),
                FileObject.thumbnail_key.is_(None),
            )
        ).all()
        print(f"待处理图片文件：{len(rows)} 个")
        for record in rows:
            try:
                response = client.get_object(bucket, record.object_key)
                try:
                    data = response.read()
                finally:
                    response.close()
                    response.release_conn()
            except Exception as exc:  # noqa: BLE001 - 对象缺失只记一条，继续处理其余
                print(f"  [跳过] 文件 {record.id}：读取对象失败（{exc}）")
                failed += 1
                continue

            processed = imageops.process(
                data,
                record.content_type,
                max_edge=0,  # 不动原图
                jpeg_quality=settings.image_jpeg_quality,
                thumbnail_edge=settings.image_thumbnail_edge,
            )
            if processed is None:
                print(f"  [跳过] 文件 {record.id}：不是可处理的静态图片（伪造头 / 损坏 / 动图）")
                undecodable += 1
                continue
            if processed.thumbnail is None:
                skipped_type += 1
                continue
            if args.dry_run:
                print(f"  [演练] 文件 {record.id}：将生成缩略图 {len(processed.thumbnail)} 字节")
                done += 1
                continue

            thumb_ext = imageops.extension_for(processed.thumbnail_content_type or "")
            thumbnail_key = f"{record.object_key.rsplit('.', 1)[0]}.thumb{thumb_ext}"
            try:
                client.put_object(
                    bucket,
                    thumbnail_key,
                    BytesIO(processed.thumbnail),
                    length=len(processed.thumbnail),
                    content_type=processed.thumbnail_content_type,
                )
            except Exception as exc:  # noqa: BLE001 - 单个对象失败不改整批
                print(f"  [失败] 文件 {record.id}：写入缩略图失败（{exc}）")
                failed += 1
                continue
            record.thumbnail_key = thumbnail_key
            if record.original_size is None:
                # 只补空白字段：已有 original_size 的记录（缩略图曾关闭时上传的图）
                # 保留真实的上传原始大小，不被「入库大小」覆盖
                record.original_size = processed.original_size
            db.commit()
            done += 1

    verb = "演练完成" if args.dry_run else "完成"
    print(
        f"补缩略图{verb}：新增 {done}，不可解码 / 动图 {undecodable}，读取失败 {failed}"
        + (f"，跳过 {skipped_type}" if skipped_type else "")
    )
    if failed:
        # 数据级不一致（DB 有行、对象存储缺对象）只报告不返回失败码：
        # 脚本本身没出错，别把部署链路里的 `make thumbs` 判成失败。
        print(f"⚠ 有 {failed} 个文件在对象存储中缺失（DB 有记录、对象不存在），请人工核查")


if __name__ == "__main__":
    main()
