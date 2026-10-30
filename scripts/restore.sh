#!/usr/bin/env bash
# 恢复（N16）：从 backups/<时间戳>/ 回灌 PostgreSQL（可选 MinIO 卷）。
#
# ⚠️ **会覆盖现有数据**：数据库会被 drop 重建，MinIO 卷内容会被删除替换。
#    必须显式确认（--yes）或在交互式终端输入 yes，避免误操作。
#
# 用法（仓库根目录，Git Bash）：
#     bash scripts/restore.sh backups/20261016-120000             # 只恢复数据库（交互确认）
#     bash scripts/restore.sh backups/20261016-120000 --yes       # 跳过交互确认（演练 / 自动化）
#     bash scripts/restore.sh backups/20261016-120000 --yes --with-minio   # 同时回灌 MinIO 卷
#
# 步骤：① （可选）停 api/worker 容器 ② drop + create 数据库 ③ pg_restore
#       ④ 迁移到 head（备份若来自旧版本，这里补齐）⑤ （可选）解包 MinIO 卷
set -euo pipefail

# Git Bash 会把容器内的绝对路径（-f /tmp/... 与 docker cp 的目标）转成 Windows 路径，
# 导致「容器里没有该目录」——关掉转换（非 MSYS 环境该变量无副作用）。
export MSYS_NO_PATHCONV=1

src="${1:-}"
with_minio="no"
confirmed="no"
for arg in "$@"; do
  case "$arg" in
    --yes) confirmed="yes" ;;
    --with-minio) with_minio="yes" ;;
  esac
done

if [[ -z "${src}" || ! -f "${src}/db.dump" ]]; then
  echo "用法：bash scripts/restore.sh backups/<时间戳> [--yes] [--with-minio]" >&2
  echo "（目录里必须有 db.dump；现有备份：）" >&2
  ls -1 backups 2>/dev/null || echo "  （还没有备份，先跑 bash scripts/backup.sh）" >&2
  exit 1
fi

PG_CONTAINER="${PG_CONTAINER:-qh_postgres}"
POSTGRES_USER="${POSTGRES_USER:-qh}"
POSTGRES_DB="${POSTGRES_DB:-qh_platform}"
project="${COMPOSE_PROJECT_NAME:-$(basename "$PWD")}"
minio_volume="${MINIO_VOLUME:-${project}_miniodata}"

echo "即将用 ${src} 覆盖数据库 ${POSTGRES_DB}"
if [[ "${with_minio}" == "yes" ]]; then
  echo "  ⚠️ 同时回灌 MinIO 卷 ${minio_volume}（卷内现有对象会被删除替换）。"
fi
if [[ "${confirmed}" != "yes" ]]; then
  read -r -p "输入 yes 继续：" answer
  [[ "${answer}" == "yes" ]] || { echo "已取消。"; exit 1; }
fi

echo "[restore] 1/5 停容器化后端（若在跑；宿主机 uvicorn 由下一步强制断连）"
docker compose --profile full stop api worker >/dev/null 2>&1 || true

echo "[restore] 2/5 重建数据库 ${POSTGRES_DB}（先断开其它连接）"
# 宿主机开发后端 / worker 也会占住连接；DROP 前强制断开（它们会自行重连）。
rebuilt="no"
for attempt in 1 2 3; do
  docker exec "${PG_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1 || true
  if docker exec "${PG_CONTAINER}" psql -U "${POSTGRES_USER}" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};" -c "CREATE DATABASE ${POSTGRES_DB};" >/dev/null 2>&1; then
    rebuilt="yes"
    break
  fi
  echo "  第 ${attempt} 次重建失败（可能仍有新连接），重试……"
  sleep 2
done
[[ "${rebuilt}" == "yes" ]] || {
  echo "[restore] 数据库重建失败：请先停止宿主机后端（make api / uvicorn）再重试。" >&2
  exit 1
}

echo "[restore] 3/5 回灌 db.dump"
docker cp "${src}/db.dump" "${PG_CONTAINER}:/tmp/qh_restore.dump"
docker exec "${PG_CONTAINER}" pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  --no-owner --no-privileges /tmp/qh_restore.dump
docker exec "${PG_CONTAINER}" rm -f /tmp/qh_restore.dump

echo "[restore] 4/5 迁移到 head（备份来自旧版本时补齐结构变更）"
( cd backend && uv run alembic upgrade head )

if [[ "${with_minio}" == "yes" ]]; then
  echo "[restore] 5/5 回灌 MinIO 卷 ${minio_volume}"
  docker volume rm "${minio_volume}" >/dev/null 2>&1 || true
  docker volume create "${minio_volume}" >/dev/null
  docker run --rm -v "${minio_volume}:/data" -v "${PWD}/${src}:/backup:ro" alpine \
    sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null; tar xzf /backup/minio-data.tar.gz -C /data"
  echo "  提示：MinIO 容器需要重启以重新挂载卷：docker compose up -d --force-recreate minio"
else
  echo "[restore] 5/5 跳过 MinIO（如需回灌加 --with-minio）"
fi

echo "[restore] 完成。检查：curl -s http://127.0.0.1:8000/api/v1/health"
echo "          重启后端 / worker / MinIO：make api 与 docker compose --profile full up -d"
