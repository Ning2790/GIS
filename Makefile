# One-stop commands. See README.md for the Chinese documentation.
# NOTE: keep this file ASCII-only -- Windows console code pages (GBK) garble UTF-8 output.
# Requires uv, pnpm and docker on PATH (see 开发环境.md).

BACKEND  := backend
FRONTEND := frontend

# Host gateway address used by the nginx containers (extra host mapping).
# Docker Desktop (Windows/macOS) injects an unreachable IPv6 record for
# host.docker.internal, which makes nginx rotate between IPv4/IPv6 and fail
# every other connect (502 + upstream temporarily disabled). Pinning an
# explicit IPv4 mapping removes that IPv6 record; on Linux host-gateway is
# already IPv4-only, so keep the keyword there.
# Env file consumed by the containerised stack (make full-up / full-down).
# Production: `cp .env.prod.example .env.prod` then `make full-up ENV_FILE=.env.prod`.
ENV_FILE ?= .env

UNAME_S := $(shell uname -s)
ifneq (,$(findstring MINGW,$(UNAME_S)))
HOST_GATEWAY ?= 192.168.65.254
else ifneq (,$(findstring MSYS,$(UNAME_S)))
HOST_GATEWAY ?= 192.168.65.254
else
HOST_GATEWAY ?= host-gateway
endif

.DEFAULT_GOAL := help

.PHONY: help
help:
	@echo "Setup"
	@echo "  make env        install backend (uv sync) + frontend (pnpm install) deps"
	@echo "  make infra      start PostgreSQL / Redis / MinIO (needs Docker)"
	@echo ""
	@echo "Develop"
	@echo "  make api        backend   http://127.0.0.1:8000/docs"
	@echo "  make web        tourist   http://localhost:5173"
	@echo "  make console    console   http://localhost:5174"
	@echo "  make portal     unified login portal   http://localhost:5175"
	@echo "  make web-gateway  nginx gateway (https://127.0.0.1:8443, profile web)"
	@echo "  make full-up    containerized api + worker + infra (profile full; see docs/部署.md)"
	@echo ""
	@echo "Quality"
	@echo "  make test       backend tests"
	@echo "  make cov        backend tests with coverage gate (see backend/pyproject.toml)"
	@echo "  make test-web   frontend unit tests (vitest)"
	@echo "  make e2e        concurrency e2e tests (needs real PG/Redis)"
	@echo "  make e2e-web    browser e2e smoke (3 flows; system Edge; isolated temp DB)"
	@echo "  make loadtest-gateway  load-test nginx gateway (http://127.0.0.1:9080, dual upstream; see docs/压测报告.md)"
	@echo "  make lint       backend lint + format check"
	@echo "  make fmt        backend auto-format"
	@echo "  make build      frontend typecheck + build"
	@echo "  make build-core build C++ compute core (needs w64devkit; optional)"
	@echo ""
	@echo "Database"
	@echo "  make migrate           apply migrations to head"
	@echo "  make migration m=text  generate migration from model changes"
	@echo "  make seed-all          one-command full demo dataset (idempotent)"
	@echo "  make db-size           table rows/sizes report (growth watch; see docs/数据增长与归档方案.md)"
	@echo "  make purge-data        retention purge (dry-run by default; ARGS=--yes to execute)"
	@echo "  make backup            dump PostgreSQL + MinIO volume into ./backups/<ts>/"
	@echo "  make restore d=<dir>   restore from a backup dir (destructive; asks for confirmation)"
	@echo ""
	@echo "Contract"
	@echo "  make openapi    export docs/api/openapi.json"

.PHONY: env
env:
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && pnpm install

.PHONY: infra
infra:
	docker compose up -d

.PHONY: web-gateway
web-gateway:
	# 与 full-up 一致带 --env-file：否则 .env.prod 里的 NGINX_UPSTREAM_CONF /
	# NGINX_BIND_IP 等开关到不了网关容器（默认读项目 .env）
	docker compose --env-file $(ENV_FILE) --profile web up -d nginx

.PHONY: api
api:
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port 8000

.PHONY: web
web:
	cd $(FRONTEND) && pnpm --filter @qh/tourist dev

.PHONY: console
console:
	cd $(FRONTEND) && pnpm --filter @qh/console dev

.PHONY: portal
portal:
	cd $(FRONTEND) && pnpm --filter @qh/portal dev

.PHONY: test
.PHONY: cov
cov:
	cd $(BACKEND) && uv run pytest -q --cov=app --cov-report=term-missing

.PHONY: test-web
test-web:
	cd $(FRONTEND) && pnpm -r test

.PHONY: test
test:
	cd $(BACKEND) && uv run pytest -q

.PHONY: e2e-web
e2e-web:
	cd $(FRONTEND) && pnpm -r build
	cd $(FRONTEND) && pnpm --filter @qh/e2e test:e2e

.PHONY: e2e
e2e:
	cd $(BACKEND) && uv run pytest tests_e2e -q

# Load-test gateway: no per-IP rate limiting (single-IP load would be blocked),
# dual-instance upstream identical to production. Never use for deployment.
.PHONY: full-up
full-up:
	docker compose --env-file $(ENV_FILE) --profile full up -d --build

.PHONY: full-down
full-down:
	# 只下线容器化后端（基础设施保留）。注意别用 `docker compose --profile full down`：
	# 那会把 postgres/redis/minio 一起摘掉（compose 的 down 作用于整个项目）。
	docker compose --env-file $(ENV_FILE) --profile full rm -sf api worker

.PHONY: loadtest-gateway
loadtest-gateway:
	docker rm -f qh_nginx_loadtest 2>/dev/null || true
	docker run -d --rm --name qh_nginx_loadtest -p 127.0.0.1:9080:80 \
		-v "$(CURDIR)/deploy/nginx/nginx.loadtest.conf:/etc/nginx/nginx.conf:ro" \
		--add-host host.docker.internal:$(HOST_GATEWAY) nginx:1.27-alpine
	@for i in 1 2 3 4 5; do \
		sleep 1; curl -sf -o /dev/null http://127.0.0.1:9080/ && echo "load-test gateway ready: http://127.0.0.1:9080" && exit 0; \
	done; echo "gateway not ready (check: docker logs qh_nginx_loadtest)"; exit 1

.PHONY: lint
lint:
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .

.PHONY: fmt
fmt:
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .

.PHONY: build
build:
	cd $(FRONTEND) && pnpm -r build

.PHONY: build-core
build-core:
	cd $(BACKEND) && uv run python ../cpp_core/build.py

.PHONY: migrate
migrate:
	cd $(BACKEND) && uv run alembic upgrade head

.PHONY: migration
migration:
	cd $(BACKEND) && uv run alembic revision --autogenerate -m "$(m)"

# One command for a full demo dataset (all steps are idempotent; safe to re-run).
# Demo accounts come from the seeds themselves (admin / merchant) plus accounts you
# register by hand; orders & after-sales are created live during the demo flow.
.PHONY: seed-all
seed-all:
	cd $(BACKEND) && uv run python scripts/seed_admin.py
	cd $(BACKEND) && uv run python scripts/seed_demo_accounts.py
	cd $(BACKEND) && uv run python scripts/seed_travel.py
	cd $(BACKEND) && uv run python scripts/seed_routes.py
	cd $(BACKEND) && uv run python scripts/seed_shop.py
	cd $(BACKEND) && uv run python scripts/seed_b2b.py
	cd $(BACKEND) && uv run python scripts/seed_knowledge.py
	cd $(BACKEND) && uv run python scripts/collect_weather.py

# 数据保留期观测 / 清理（见 docs/数据增长与归档方案.md）
.PHONY: db-size
db-size:
	cd $(BACKEND) && uv run python scripts/db_size_report.py

.PHONY: purge-data
purge-data:
	cd $(BACKEND) && uv run python scripts/purge_data.py $(ARGS)

# Regenerate the committed product images (only needed when changing their style).
.PHONY: seed-images
seed-images:
	cd $(BACKEND) && uv run python scripts/make_seed_images.py

# 为存量图片补缩略图（图片增强上线前上传的文件；幂等，可反复运行）。
.PHONY: thumbs
thumbs:
	cd $(BACKEND) && uv run python scripts/make_thumbnails.py

# Backup / restore (see docs/部署.md and scripts/*.sh for details and caveats).
.PHONY: backup
backup:
	bash scripts/backup.sh

.PHONY: restore
restore:
	bash scripts/restore.sh "$(d)"

.PHONY: openapi
openapi:
	cd $(BACKEND) && uv run python scripts/export_openapi.py
