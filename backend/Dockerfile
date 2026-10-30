# 后端镜像（N15 全栈容器化）。
#
# 用途：新机器 / 演示环境一条命令起全栈（`make full-up`）；**宿主机开发流程不变**（仍 `make api`）。
# 构建：docker compose --profile full build   （或 docker build -t qh-platform-api:0.1.0 backend）
#
# 说明：
# - 基于 python:3.13-slim + uv（与开发机同大版本），依赖严格按 uv.lock 安装；
# - 镜像内**不含 C++ 扩展**（仓库里的 qh_core.*.pyd 是 Windows 产物）：app/core/compute.py
#   会在导入失败时自动回退 Python 实现，功能一致、性能略降；如需 Linux 原生扩展见 docs/部署.md；
# - 非 root 运行（uid 10001）；迁移入口见 docker-entrypoint.sh。

# ---------- 依赖层（缓存友好） ----------
FROM python:3.13.16-slim AS builder

# uv 钉到次版本：AGENTS.md 约定「只要求大版本一致」（0.13.x），补丁号随官方镜像滚动
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
# 只复制锁文件：源码变动不会让依赖层失效
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ---------- 运行时层 ----------
FROM python:3.13.16-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 固定 uid：挂载卷 / 日志目录的权限在多台机器上保持一致
RUN useradd --create-home --uid 10001 app

WORKDIR /app
# /app 目录本身也要属 app：否则非 root 进程无法在其中写文件（celery beat 的调度文件就在这里）
RUN chown app:app /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app pyproject.toml alembic.ini ./
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app scripts ./scripts
COPY --chown=app:app docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Windows 检出可能带 CRLF（shebang 会失效）：构建时统一剥掉行尾回车，与 .gitattributes 双保险
RUN tr -d '\r' < /usr/local/bin/docker-entrypoint.sh > /tmp/entrypoint.sh \
    && mv /tmp/entrypoint.sh /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# 容器内不需要 setuid 工具（su / mount / passwd 等），清掉可减少提权面
RUN find / -xdev -perm -4000 -type f -delete

USER app
EXPOSE 8000

# 入口会按 RUN_MIGRATIONS（默认 1）先跑 alembic upgrade head
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
