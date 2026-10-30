#!/bin/sh
# 容器入口（N15）：按需先跑数据库迁移，再执行 CMD。
#
# RUN_MIGRATIONS=0 可跳过——多副本部署时只在其中一个实例上跑迁移，避免并发执行；
# worker 容器由 compose 显式设为 0（迁移交给 api）。
set -e

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  # 新建库 / 外部托管 PG 可能没有 postgis 扩展，而迁移依赖它（幂等，非 PG 跳过；失败即退出）
  python scripts/ensure_postgis.py
  echo "[entrypoint] 数据库迁移（带分布式锁，多副本安全；如需跳过设 RUN_MIGRATIONS=0）"
  python scripts/run_migrations.py
fi

exec "$@"
