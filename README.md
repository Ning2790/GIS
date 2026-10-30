# 青海"旅游 + 农产品"平台

一个把**游客、农户、农产品加工企业**连接起来的 Web 平台：

- **智能行程规划** —— AI 按偏好、预算、体力生成个性化路线，含地图导航与风险评估
- **行前装备建议** —— 结合实时气象、土壤、海拔、气压给出"来青海要带什么"
- **特产商城（B2C）** —— 农户 / 商家入驻，游客浏览下单，平台内闭环交易
- **供需撮合（B2B）** —— 农户与企业凭资质注册，平台**只提供信息服务、不做交易**

需求原文与完整方案见 `技术方案与架构.md`；环境配置见 `开发环境.md` 与 `AGENTS.md`。

**任务与进度**：做什么、还剩什么 → `docs/任务清单.md`；怎么动手、怎么自测 → `docs/AI任务手册.md`（给 AI 与开发者的执行手册）。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13 + FastAPI（模块化单体）+ SQLAlchemy + Alembic |
| 数据库 | PostgreSQL 16 + PostGIS（开发期可切 SQLite） |
| 缓存 / 队列 | Redis 7 |
| 对象存储 | MinIO |
| 前端 | Vue 3 + TypeScript + Vite（pnpm workspace，双应用） |
| 计算核心 | C++（pybind11，当前为占位） |
| 部署 | Docker Compose + Nginx |

---

## 快速开始

```bash
# 1. 依赖
make env                 # = uv sync + pnpm install
cp .env.example .env     # 按需修改

# 2. 基础设施（需已安装 Docker；未装可跳过，默认用 SQLite）
make infra               # 起 PostgreSQL / Redis / MinIO

# 3. 建表
make migrate

# 4. 起服务
make api                 # 后端 http://127.0.0.1:8000/docs
make web                 # 游客端 http://localhost:5173
make console             # 控制台 http://localhost:5174
make portal              # 统一登录 http://localhost:5175
```

`make` 可查看全部命令。

---

## 目录结构

```
xiangmu/
├── backend/                 FastAPI 模块化单体
│   ├── app/
│   │   ├── main.py          应用入口、中间件、异常处理
│   │   ├── core/            公共层：配置 / 安全 / 响应信封 / 错误码 / 日志 / 分页 / 大模型入口
│   │   ├── db/              引擎、会话、模型登记表
│   │   ├── api/
│   │   │   ├── deps.py      跨模块依赖（当前用户、角色校验）
│   │   │   └── v1/router.py 路由聚合点
│   │   └── modules/         业务模块，每模块 5 个文件
│   ├── alembic/             数据库迁移
│   ├── tests/
│   └── scripts/             openapi 导出等工具
├── cpp_core/                C++ 计算核心（占位，未接入构建）
├── frontend/                pnpm workspace
│   ├── apps/tourist/        游客端
│   ├── apps/console/        商户端 + 管理后台
│   ├── apps/portal/         统一登录门户（游客 / 商户 / 企业）
│   └── packages/
│       ├── ui/              共享组件
│       └── api-client/      接口请求封装
├── docs/
│   ├── api/openapi.json     接口契约（后端导出）
│   ├── database.md          数据模型
│   ├── AI任务手册.md        任务卡（改动范围 / 步骤 / 自测 / 判据）
│   └── 任务清单.md          任务总表与进度
├── scripts/check-env.sh     环境自检
├── docker-compose.yml
└── Makefile
```

---

## 开发约定（重要）

### 1. 模块边界 —— 防冲突的核心

每个后端模块固定 5 个文件，结构完全一致：

```
modules/<模块名>/
├── router.py      路由（对外唯一出口）
├── service.py     业务逻辑
├── repository.py  数据访问
├── models.py      ORM 表
└── schemas.py     请求 / 响应模型
```

**三条铁律**
1. 跨模块调用**只能走对方的 `service`**，禁止 import 别人的 `repository` / `models`。
2. 一张表只属于一个模块，其他模块不得直接读写。
3. 新增模块后，到 `app/api/v1/router.py` 挂载路由、到 `app/db/models_registry.py` 登记模型。

### 2. 接口约定

- 所有响应统一为 `{code, msg, data}`：`code == 0` 成功，非 0 为业务错误码（见 `app/core/errors.py`）。
- 接口实现用 `ok(data)` 返回，抛 `AppError` 子类报错，**不要自己拼字典**。
- 路由依赖用 `DbSession` / `CurrentUser` 类型别名（见 `app/api/deps.py`），不要写 `= Depends(...)`。
- 列表接口统一用 `app/core/pagination.py` 的 `PageParams` + `page_data`：请求参数 `page` / `page_size`（上限 100），响应 `data = {items, total, page, page_size}`。
- 接口改动后执行 `make openapi`，把新的 `docs/api/openapi.json` 一并提交。
- 前端所有请求走 `@qh/api-client`，不要在组件里直接 `fetch`。

### 3. 数据库变更

改模型 → `make migration m="描述"` → `make migrate` → 提交迁移文件。
新模型记得登记到 `app/db/models_registry.py`。详见 `docs/database.md`。

---

## 5 人分工

| 角色 | 负责目录 |
|---|---|
| 后端 A | `modules/auth` `users` `cs` `admin` |
| 后端 B | `modules/travel` `map` `gear` `ai` + `cpp_core` |
| 后端 C | `modules/shop` `b2b` |
| 前端 A | `apps/tourist` |
| 前端 B | `apps/console` |
| **公共层（改动需评审）** | `app/core` `app/api` `app/db` `packages/*` `docs/api` |

公共层是所有人共用的地基，改动请单独开 PR 并说明影响面；业务代码请只在自己的模块目录内修改。

---

## 分支与提交

- 分支：`main`（稳定）+ `feature/<模块>-<描述>`，通过 PR 合并。
- CI（`.github/workflows/ci.yml`）会自动跑后端 lint + 测试、前端类型检查 + 构建，**CI 不绿不合并**。
- 提交前 `pre-commit` 会自动格式化；手动检查用 `make lint`。
- 并发行为用真 PostgreSQL/Redis 的 e2e 套件验证：`make e2e`（需先 `docker compose up -d`；
  它不在 `make test` 的 SQLite 环境里跑，两者分开执行）。

---

## 当前进度

已完成（可运行的最小闭环）：
- 后端骨架、统一响应信封与错误码、数据库接入与迁移
- 双角色注册登录：游客可注册登录；商户 / 企业需资质，注册后待审核
- JWT 鉴权与受保护接口（`/users/me`）
- 用户列表（管理员）：分页 + 角色 / 状态 / 关键词过滤
- 资质审核（`admin`）：待审核列表 / 通过 / 驳回；通过后商户 / 企业即可登录。
  首个管理员用 `cd backend && uv run python scripts/seed_admin.py` 创建
- 运营后台（`admin`）：审计日志（`audit_logs`，含操作人 / 动作 / 目标类型 / 目标；
  公共入口 `record_action`，客服流转与业务动作（订单取消 / 支付回调 / 路线增删改）亦入审计，
  查询支持按动作与目标类型过滤）、用户启用 / 禁用
- 登录会话与令牌刷新：访问令牌 30 分钟 + 刷新令牌 30 天（`/auth/refresh` 轮换、`/auth/logout` 撤销）
- 设备绑定与二次访问自动登录（需求 4.2）：登录登记设备（`device_bindings`），刷新时会话与设备必须
  匹配；「记住我」= 30 天、未勾选 = 12 小时（`REFRESH_TOKEN_SHORT_EXPIRE_HOURS`）；两端可查看
  已登录设备并逐个移除（移除即撤销该设备名下全部会话，入审计 `device.revoke`）
- 在线客服（`cs`，需求 4.4）：AI 自动应答（统一入口 `app/core/llm.py`，默认 mock 免密钥）
  → 转人工队列 → 商家（商户 / 企业）接入与人工回复
- 景点与门票（`travel`）：景点列表（分页 + 城市 / 关键词过滤）与详情（含票种）；
  演示数据 `cd backend && uv run python scripts/seed_travel.py`
- 地图三图与点位（`map`）：卫星 / 行政 / 地形底图配置 + 点位查询（支持视野 bbox 过滤，
  PostgreSQL 走 PostGIS 的 `geom` 列 + GIST 索引）
- 装备建议（`gear`，需求 2.2）：环境快照（气温 / 土壤湿度 / 海拔 / 气压）采集
  （Celery Beat 定时或 `scripts/collect_weather.py` 手动；**Open-Meteo 真实气象源**，免密钥，
  断网自动回退模拟源，`--refresh` 可把历史模拟数据换新）+ 公开的建议接口
- AI 问答（`ai`）：会话记录 + **RAG 向量检索**（N12：向量优先、关键词兜底；命中随响应回传，
  游客端展示「参考平台知识」卡片；嵌入默认 mock 确定性实现，接真实嵌入模型只改 `.env`）
  + 联网搜索适配器（mock）
  + SSE 流式输出；大模型统一走 `app/core/llm.py`（默认 mock，接云端只改 `.env`）
- 供需撮合（`b2b`，需求 2.4）：农户 / 企业发布供给与需求（需资质），浏览公开；
  规则匹配（品类一致 + 地区 / 数量加分）仅供需求发布者——**平台只做信息服务，不碰交易**
- C++ 计算核心（`cpp_core`）：Haversine 距离、推荐打分、行程选点打分（偏好匹配加权）
  与路径总里程，pybind11 暴露为 `qh_core`；`make build-core` 构建（w64devkit + Ninja），
  未编译或扩展版本过旧时 `app/core/compute.py` 自动回退 Python 实现（CI 无需编译器）；
  景点列表支持 `near=lng,lat` 按距离排序，行程生成按偏好相关性选点，
  路线 / 行程详情给出全程里程
- 行程规划（`travel`）：AI 生成个性化行程（天数 / 预算 / 偏好 / 体力）+ 风险提示
  （走 `app/core/llm.py`，失败有兜底），支持增删停靠点与排序；
  预设路线（精选线路列表 / 详情 + 一键套用为我的行程，演示数据
  `cd backend && uv run python scripts/seed_routes.py`）
- 特产商城（`shop`）：上架（可带主图，经 `POST /files?public=true` 上传公开图片）/
  列表 / 详情（公开）、购物车、直购与结算（幂等键防重复下单；**收货信息必填并随订单快照**）、
  待支付订单**超时自动取消**（默认 30 分钟，`ORDER_EXPIRE_MINUTES`；Celery Beat 每分钟扫描，
  库存同事务回补 + 支付单置失败 + 审计 `order.expire`）、
  商户**发货**（承运商 + 运单号必填）→ 买家**确认收货**（或签收后 7 天 / 发货后 15 天兜底自动确认，
  Celery Beat 每小时扫描 + `scripts/auto_confirm_orders.py`；状态机 `created → paid → shipped → completed`）、
  防超卖双保险（Redis 预扣闸门 + 数据库条件更新，Redis 不可用自动降级）、
  订单查询（买家 / 商家 / 管理员）、支付单占位（管理员可模拟回调）与
  订单取消（仅待支付；原子翻转让并发双取消只生效一次，库存同事务回补并同步闸门；
  **售后单**：已支付起可申请（已完成订单 15 天内），商户受理 / 完成 / 拒绝（理由必填），
  买家在受理前可撤销，双方留言跟踪；平台不经手资金——退款 / 换货线下或经第三方处理；
  在线客服作为独立入口保留）；
  个人中心「收货地址」簿（默认地址、下单自动带出）与「我的售后」
- 前端游客端（`apps/tourist`，设计基线「C · 现代极简」，`packages/ui` 设计变量 + 基础组件）：
  首页、登录 / 注册（登录态自动刷新）、个人中心（改昵称 / 改密码，改密码踢出其他设备）、
  景点列表 / 详情（筛选 / 距离排序 / 票种）、
  地图（Leaflet 三图切换 + 视野 bbox 拉点）、装备建议（环境速览 + 装备清单）、
  特产商城（商品带图 / 购物车 / 下单 / 支付占位 / 我的订单 / 取消订单 / 申请售后）、
  精选路线（列表 / 每日安排 / 套用为我的行程）、
  AI 问答（SSE 流式 + 会话列表）、行程规划（生成 + 停靠点编辑）、在线客服（AI 应答 / 转人工）
- 前端管理端（`apps/console`，Element Plus + 按角色分流菜单）：首页概览（按角色聚合的
  经营看板：商品 / 订单 / 今日成交 / 库存预警 / 待审核 / 客服排队 / 最近操作）、
  商户侧商品管理（含主图上传 / 编辑改价 / 库存）、订单管理 / 供需发布与匹配 / 客服工作台；
  管理员侧路线管理（预设路线增删改） / 资质审核（含资质文件） / 用户管理 / 审计日志 /
  全平台订单与模拟支付回调
- 统一登录门户（`apps/portal`，生产 `/portal/`）：游客 / 商户 / 企业三类身份登录与注册，
  也是全平台唯一页面入口；游客端 / 控制台的 `/login` 仅作跳转页。未登录访问受保护页面会带
  `redirect` 参数跳到门户，登录后回到原页面；开发 / E2E 跨端口用一次性 hash 交接登录态
  （含设备标识），生产三端同源直接共享
- 前端基础设施：`packages/api-client` 分模块封装（请求体类型由 OpenAPI 生成）+ 401 自动刷新重放、
  Pinia 登录态 / 购物车、路由守卫（登录 + 角色）
- 需求对照表（`docs/需求对照表.md`）：需求 1.1–5.4 逐条 → 实现 → 验收方式（含挂起项与演示操作索引）
- 交付材料：演示脚本（`docs/演示脚本.md`，含完整版 / 精简版 / 应急与截图索引）、
  两端实拍截图（`docs/screenshots/`，39 张）、答辩 PPT（13 页，构建脚本
  `docs/答辩PPT-构建脚本.js` 可重跑生成，产物不入库）
- 前端单元测试（vitest **107 项**：api-client 请求层 10 / UI 组件 11 / 游客端 41（store 与页面、
  收藏/历史/推荐/热词/离线横幅）/ 控制台 45（登录态、商品、订单、售后、路线、概览监控卡片）；`make test-web`）
- 后端覆盖率门禁（`make cov`：只统计 `app/`，行覆盖率 ≥88%，实测 **93.3%**，317 项）
- 浏览器端 E2E 冒烟（`make e2e-web`：Playwright + 系统 Edge，三条链路——下单全链路 /
  旅行链路 / 客服链路——跑在独立 SQLite 临时库上，与演示库隔离）
- 运行指标与监控：`/metrics`（Prometheus 文本，网关仅内网可读）+ 管理员概览页监控卡片
  （累计请求 / 服务端错误 / P95 与平均延迟 / 限流命中 / 排队拒绝 / 在途与容量 / 闸门回补）
- 日志与请求追踪：dev 可读、非 dev 单行 JSON；`X-Request-ID` 由网关生成并贯穿
  （响应头回带，网关访问日志与后端日志同 ID 可对齐）；慢请求告警（默认 500ms，SSE 豁免）；
  日志脱敏（手机号 / 令牌 / 异常堆栈）
- 承载能力压测补全 4.3 三档 + 双实例复测（读 1189 req/s、交易 81 单/s、AI 5.4 次/s（mock）；
  双实例同口径对照与网关限流档见 `docs/压测报告.md`）
- 承载加固：闸门容量与连接池对齐（交易 50 / 认证 20 / 查看 200，实测池超时归零）、
  数据库不可达 3 秒内回 503（提交后失败改回 500、不诱导重试）、上游 least_conn +
  显式 IPv4 映射（修掉容器内不可达 IPv6 导致的偶发 502）
- CI 与接口契约导出
- 并发正确性审计与修复（幂等下单 / 匹配 / 购物车 / 采集 / 停靠点等并发路径，
  详见 `docs/代码审计报告.md`）
- 事务约定全仓统一：所有模块 repository 只 flush、service 控制提交
  （shop / ai / travel / b2b / admin / cs / auth / users；刷新轮换与客服流转审计均在单事务内）

待建设：
- 真实支付网关接入（当前为支付单占位 + 管理员模拟回调）
