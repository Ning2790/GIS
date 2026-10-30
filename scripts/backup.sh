#!/usr/bin/env bash
# 备份（N16）：PostgreSQL 逻辑备份 + MinIO 数据卷打包，输出到 backups/<时间戳>/。
#
# 用法（仓库根目录，Git Bash）：
#     bash scripts/backup.sh                 # 默认备份到 ./backups/
#     BACKUP_ROOT=/d/backups bash scripts/backup.sh
#
# 产出（同一时间戳目录下）：
#   db.dump          —— pg_dump 自定义格式（-Fc，可用 pg_restore 选择性恢复）
#   minio-data.tar.gz—— MinIO 数据卷打包（资质文件、商品图等对象）
#   MANIFEST.txt     —— 时间 / 库名 / 版本 / 大小 / 当前 git 提交，便于核对
#
# 说明：
# - 用**容器内的 pg_dump**（与运行中的 PG 同版本），避免本机 psql 版本不一致；
# - MinIO 卷用一次性 alpine 容器打包，不依赖 mc 客户端；
# - 恢复流程见 `scripts/restore.sh` 与 docs/部署.md「备份与恢复」。
set -euo pipefail

# Git Bash 会把容器内的绝对路径（-f /tmp/... 与 docker cp 的目标）转成 Windows 路径，
# 导致「容器里没有该目录」——关掉转换（非 MSYS 环境该变量无副作用）。
export MSYS_NO_PATHCONV=1

BACKUP_ROOT="${BACKUP_ROOT:-backups}"
PG_CONTAINER="${PG_CONTAINER:-qh_postgres}"
POSTGRES_USER="${POSTGRES_USER:-qh}"
POSTGRES_DB="${POSTGRES_DB:-qh_platform}"

# 卷名 = compose 项目名 + 卷名；项目名默认取仓库目录名（compose 的默认行为）
project="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
minio_volume="${MINIO_VOLUME:-${project}_miniodata}"

if ! docker volume inspect "${minio_volume}" >/dev/null 2>&1; then
  echo "[backup] 找不到 MinIO 卷 ${minio_volume}" >&2
  echo "         可用 MINIO_VOLUME=<卷名> 指定；确认 docker compose up -d 已起过 MinIO。" >&2
  docker volume ls --format '  现有卷：{{.Name}}' >&2
  exit 1
fi

stamp="$(date +%Y%m%d-%H%M%S)"
dest="${BACKUP_ROOT}/${stamp}"
mkdir -p "${dest}"

echo "[backup] 目标目录：${dest}"

echo "[backup] 1/3 PostgreSQL（${POSTGRES_DB}）→ db.dump"
docker exec "${PG_CONTAINER}" pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc \
  -f /tmp/qh_backup.dump
docker cp "${PG_CONTAINER}:/tmp/qh_backup.dump" "${dest}/db.dump"
docker exec "${PG_CONTAINER}" rm -f /tmp/qh_backup.dump

echo "[backup] 2/3 MinIO 数据卷（${minio_volume}）→ minio-data.tar.gz"
docker run --rm -v "${minio_volume}:/data:ro" -v "${PWD}/${dest}:/backup" alpine \
  tar czf /backup/minio-data.tar.gz -C /data .

echo "[backup] 3/3 写入清单"
{
  echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "数据库: ${POSTGRES_DB}（容器 ${PG_CONTAINER}）"
  echo "PG 版本: $(docker exec "${PG_CONTAINER}" postgres --version)"
  echo "MinIO 卷: ${minio_volume}"
  echo "git 提交: $(git rev-parse --short HEAD 2>/dev/null || echo '（非 git 目录）')"
  echo "db.dump 大小: $(du -h "${dest}/db.dump" | cut -f1)"
  echo "minio 大小: $(du -h "${dest}/minio-data.tar.gz" | cut -f1)"
} > "${dest}/MANIFEST.txt"

echo "[backup] 完成："
cat "${dest}/MANIFEST.txt"
