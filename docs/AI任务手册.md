# AI 任务手册

> 给 **AI 编程会话**与开发者的执行手册：每张任务卡含 **改动范围 / 前置依赖 / 步骤 / 自测命令 / 完成判据 / 人工复核点**。
> 总进度与任务总表见 `docs/任务清单.md`；协作流程与红线见 `docs/开发流程.md`；环境见 `开发环境.md`。

---

## 一、每次开工前，先把这些喂给 AI（固定动作）

1. **必读四样**：`AGENTS.md`（环境与约定）、`README.md`（模块边界）、`docs/api/openapi.json`（接口契约）、**样板代码**——照 `modules/auth` + `modules/users` 的写法（分层、响应信封、错误码、依赖别名）。
2. **边界句**（原样放进提示词）：「**只改本卡"改动范围"列出的文件，不要动 core/、api/、db/ 和别人的模块**」。
3. **生成后立刻跑门禁**：`make lint && make test`；接口变动再 `make openapi` 并把契约一起提交。
4. **关键逻辑人工复核**：支付、库存扣减、权限、认证相关代码要逐行看（见各卡"人工复核点"）。
5. **公共层改动**（`app/core`、`app/api`、`app/db`、`packages/*`、`docs/api`）：单独提交，PR 里说明影响面。

## 二、标准流水线（新增/完善任何模块都照这个顺序，**不能反**）

模型 → 登记 `app/db/models_registry.py`（**漏了这步迁移检测不到新表**）→ `make migration m="描述"` + `make migrate` →
`schemas.py` → `repository.py` → `service.py` → `router.py`（**删除本模块的 `_status` 占位，并从 `tests/test_health.py` 的占位断言里移除该模块**）→
`tests/test_<模块>.py` → `make lint && make test` → `make openapi` → 提交（一个 PR 一个功能）。

## 三、现成的公共设施（直接用，别再造）

| 设施 | 位置 | 用法 |
|---|---|---|
| 响应信封 | `app/core/response.py` | 成功 `return ok(data, msg="...")`；失败抛 `app/core/errors.py` 的 AppError 子类（不要手拼字典） |
| 分页 | `app/core/pagination.py` | 路由声明 `page: PageParams`；service 用 `pagination.paginate(db, stmt, page)`；响应形状 `{items, total, page, page_size}` |
| 大模型入口 | `app/core/llm.py` | `llm.chat([{"role": "user", "content": "..."}])`；默认 mock 免密钥，接云端只改 `.env` |
| 鉴权依赖 | `app/api/deps.py` | `DbSession` / `CurrentUser` / `require_roles("merchant", "enterprise")`（一律 Annotated 风格，不要写 `= Depends(...)`） |
| 用户数据 | `modules/users/service.py` | 跨模块只调对方 `service`；首个管理员用 `scripts/seed_admin.py` 创建 |
| 测试夹具 | `tests/conftest.py` | 临时 SQLite、`client` fixture；测试不要连 PG |
| 迁移安全 | `alembic/env.py` | PostGIS 系统表过滤已配好——**不要删 include_name / include_object 与 SET search_path**，否则 autogenerate 会生成删系统表的破坏性迁移 |

---

## 四、任务卡（按依赖顺序；每张卡都可以交给一个独立的 AI 会话执行）

### B1 · travel 景点与门票（第一周任务，P0）
- **需求**：2.1（平台展示景点与门票价格）
- **依赖**：无（公共设施已就绪）
- **改动范围**：`backend/app/modules/travel/` 5 个文件 + `backend/tests/test_travel.py`（新增）+ `backend/scripts/seed_travel.py`（新增）+ `models_registry.py` 登记 + `docs/api/openapi.json`
- **表（建议，可微调）**：`attractions`（id、name、city 索引、description、latitude / longitude、cover_image 可空、created_at）；`tickets`（id、attraction_id 外键索引、name、price Numeric(10,2)、description 可空、created_at）
- **设计决定**：地理字段先用 **latitude / longitude 两个 float**；PostGIS 几何列留到 B3（map）再迁——测试跑 SQLite，Geometry 类型不兼容
- **接口**：`GET /api/v1/travel/attractions`（分页 + `city` / `keyword` 过滤，公开）、`GET /api/v1/travel/attractions/{id}`（含票种列表，公开）
- **自测命令**：`make lint && make test`；`make openapi`；起服务后 `curl` 列表与详情
- **完成判据**：分页形状与其他列表一致；详情含票种；契约含新接口且无 `travel/_status`；CI 绿
- **人工复核点**：字段与契约命名一致性；过滤条件边界

### C1 · shop 商品与下单（第一周任务，P0）
- **需求**：2.3（B2C 商城，第一周只做最小下单）
- **依赖**：无（商户账号已有来源：admin 审核通过后即可登录）
- **改动范围**：`backend/app/modules/shop/` 5 个文件 + `backend/tests/test_shop.py`（新增）+ `models_registry.py` + `docs/api/openapi.json`
- **表（建议）**：`products`（id、merchant_id 索引、name、description、price Numeric(10,2)、stock、status、created_at）；**最简 `orders`**（id、user_id、product_id、quantity、amount、status、created_at）——下单要落库才有闭环；完整订单体系见 C2
- **接口**：`GET /api/v1/shop/products`（分页 + keyword；可含 `merchant_id` 过滤）、`GET /api/v1/shop/products/{id}`、`POST /api/v1/shop/orders`（登录用户；扣库存）
- **库存扣减（第一周）**：条件更新防超卖——`UPDATE products SET stock = stock - :qty WHERE id = :id AND stock >= :qty`，rowcount 为 0 即库存不足返回 409；不要先读后写
- **自测命令**：`make lint && make test`；`make openapi`
- **完成判据**：库存不足 409、成功后库存确实减少、下单归属登录用户；契约更新；CI 绿
- **人工复核点（重点）**：库存扣减逻辑逐行看；订单金额计算

### B2 · travel 路线与行程（P1）
- **需求**：2.1（AI 按偏好 / 预算 / 体力生成个性化路线 + 风险评估；游客可自主增减地点）
- **依赖**：B1；`core/llm.py`（已就绪）
- **改动范围**：travel 模块既有文件 + `routes` / `route_stops` / `itineraries` 三表（迁移）+ 测试
- **要点**：生成接口用 `llm.chat`，返回结构化的路线建议（mock 提供方返回确定性结果便于测试）；行程增删地点是本地编辑操作，不需要模型
- **完成判据**：生成 / 调整 / 详情接口全通；LLM 不可用时有清晰报错；契约更新

### B3 · map 三图与点位（P1）
- **需求**：2.1（卫星 / 行政 / 地形三图与点位查询）
- **依赖**：B1
- **要点**：给 `attractions` 增加 PostGIS 几何列（**新迁移**，不要改历史迁移）；点位查询接口按范围（bbox）过滤；开发库是 PostGIS、测试是 SQLite——几何相关逻辑放 repository 并以 SQLite 兼容方式写（或用 dialect 判断），测试至少覆盖业务分支
- **完成判据**：点位查询正确；迁移在 PG 上验证通过；契约更新

### B4 · gear 装备建议与气象采集（P1）
- **需求**：2.2（结合气象 / 土壤 / 海拔 / 气压给行前装备建议）
- **依赖**：先 `uv add celery`（依赖变更走 uv，不要手写）；Redis 已起（docker-compose）
- **改动范围**：`modules/gear/` + `weather_snapshots` / `gear_recommendations` 两表 + 采集任务（Celery Beat）+ 测试
- **要点**：采集可以是模拟数据源打底（真实气象源后续替换）；建议生成规则先走确定性规则 + 可选 `llm.chat` 润色
- **完成判据**：快照落库、建议接口按地点 / 日期返回；任务可手动触发一次验证

### B5 · ai 增强（P1）
- **需求**：2.1 / 客服的 AI 能力升级
- **依赖**：`core/llm.py`（已就绪）
- **改动范围**：`modules/ai/` + `ai_conversations` 表 + 测试
- **要点**：会话记录、RAG（先做最简版：把知识文本拼接进 prompt）、联网搜索适配器（接口 + mock 实现）、流式输出（SSE，前端另行跟进）
- **完成判据**：提问 / 会话列表 / 会话详情按契约返回；契约更新

### B6 · cpp_core 接入（P2）
- **需求**：5.x（算力核心用 C++）
- **依赖**：w64devkit（GCC/CMake，已装）；**注意**：没有 w64devkit 的机器跑不了构建——CI 里要么装要么跳过该步
- **要点**：先接一个最简函数（如景点推荐打分），pybind11 绑定 + Python 侧回退实现（未编译时用 Python 版，保证测试与 CI 可跑）
- **完成判据**：`make build-core` 编译通过（本机）；Python 侧两种实现可切换；业务模块只调封装层
- **扩展记录（2026-10-13）**：新增行程选点打分 `planning_score` / `planning_scores`
  （`cpp_core/src/planning.cpp`；偏好为空 → 0，全名 → 100，名称包含偏好 → 70 + 覆盖度 × 20，
  整句提到景点名 → 65，城市命中 → 60）。`travel.generate_itinerary` 的选点改走该打分。
  **注意**：扩展是二进制产物，拉下新代码后需重新 `make build-core`（编译前先停后端，`qh_core.pyd` 会被占用）；
  `compute.py` 对新增函数做函数级探测，旧版扩展缺函数时自动回退 Python，不再报 AttributeError

### C2 · shop 交易闭环（P1）
- **需求**：2.3 + 4.3（承载：500 人同时交易）
- **依赖**：C1；Redis（已起）
- **改动范围**：shop 模块既有文件 + `inventory` / `carts` / `order_items` / `payments` 表（+ 完善 `orders`）+ 测试
- **要点**（架构文档已定的方案）：数据库事务 + **Redis 原子扣减**防超卖（第一周的条件更新继续保留作兜底）；**订单接口幂等**（幂等键，重复提交返回同一订单）；支付走第三方、平台不做资金池——先做"支付单 + 回调占位"的最小实现
- **人工复核点（逐行）**：库存与支付相关代码；金额计算；幂等键生成
- **完成判据**：并发下单不超卖（写并发测试）；重复提交幂等；契约更新

### C3 · b2b 供需撮合（P1）
- **需求**：2.4（农户 ↔ 企业信息撮合，**平台只提供信息服务、不做交易**）
- **依赖**：无（商户 / 企业账号已就绪）
- **改动范围**：`modules/b2b/` + `b2b_supplies` / `b2b_demands` / `b2b_matches` 三表 + 测试
- **要点**：表里**不要出现订单 / 支付字段**；发布需 merchant / enterprise 角色（`require_roles`）；匹配先做规则匹配（品类 + 地区 + 数量）
- **完成判据**：发布 / 浏览 / 匹配接口全通；权限正确；契约更新

### B7 · travel 预设路线（已完成 2026-10-13）
- **需求**：2.1（平台精选线路，游客可套用后自行调整）
- **改动范围**：`modules/travel/` 既有文件 + `routes` / `route_stops` 两表（迁移 `15d201b9eefc`）+ `scripts/seed_routes.py` + 测试；前端游客端 `/routes`、`/routes/:id`
- **接口**：`GET /api/v1/travel/routes`（公开，分页 + theme 过滤，与景点列表同样缓存 60s）、
  `GET /api/v1/travel/routes/{id}`（公开，含停靠点与景点坐标）、
  `POST /api/v1/travel/routes/{id}/apply`（登录用户，整条路线复制为个人行程，停靠点 day / position 原样带入）
- **要点**：平台路线与个人行程分开存（路线是平台资产，套用是拷贝，之后互不影响）；
  套用不调模型（确定性复制，风险提示用兜底文案）；seed 按路线名去重、停靠点整体重建（幂等可重跑）
- **完成判据**：列表 / 详情 / 套用接口全通；seed 幂等；套用后行程可编辑；契约更新

### C4 · shop 订单取消与售后（已完成 2026-10-13）
- **需求**：2.3（订单闭环）
- **改动范围**：`modules/shop/` 既有文件 + 测试；前端游客端订单详情 / 列表、管理端订单状态
- **接口**：`POST /api/v1/shop/orders/{id}/cancel`（买家本人，仅待支付）
- **要点**：取消用**原子条件更新**（`status=created` 才翻转），并发双取消只有一个成功、库存不会被回补两次；
  库存回补与状态翻转同一事务并记库存流水（reason=cancel），提交后按 DB 权威值同步 Redis 闸门；
  **已支付订单不可取消**（平台不做资金池），售后诉求走在线客服：前端「申请售后」自动建会话并带入订单上下文
- **完成判据**：取消后库存回补、重复取消 409、已支付 409、他人 404；两端页面状态齐全；契约更新

### D1 · 事务约定统一（travel / b2b，已完成 2026-10-13）
- **约定**：repository **只 flush 不 commit**，事务边界统一由 service 控制（shop / ai 已是此约定）
- **改动范围**：`modules/travel/repository.py`、`modules/b2b/repository.py` 及对应 service、`scripts/seed_travel.py`
- **要点**：停靠点全量替换 / 匹配记录替换的「先删后插」仍为单事务；
  `b2b.replace_matches` 的唯一约束冲突处理从 commit 移到 flush（撞约束即整体回滚，保留先到者结果，返回是否落库）；
  `generate_itinerary` 把模型调用移出事务（外部调用不占连接与写锁）；
  维护脚本（seed）在调用 flush-only 的 repository 函数后自行 commit
- **验证**：PG 上 4 并发匹配仍 4×200 无重复行；行程生成 / 替换 / 套用 / 删除、供需发布 / 关闭 live 全通
- **仍未统一（后续）**：cs / auth / users / admin 的 repository 仍在内部 commit，改动前先评估登录链路风险

### D2 · 审计日志覆盖扩展（已完成 2026-10-13）
- **公共入口**：`admin.service.record_action(db, *, actor_id, action, target_id, target_type="user", detail=None, commit=True)`
  ——其他模块的关键操作只能经它写入 `audit_logs`（跨模块只走 service）；
  `commit=False` 时只 flush，可把日志并入调用方事务
- **已接入**：客服流转 `cs.transfer` / `cs.claim` / `cs.release` / `cs.close`（target_type=`cs_session`）；
  管理员原有 `review.approve|reject`、`user.disable|enable` 改走同一入口
- **查询**：`GET /api/v1/admin/audit-logs` 新增 `target_type` 过滤；管理端审计页补「客服会话」过滤与新动作标签
- **完成判据**：会话流转产生日志（含操作人 / 目标 / 可读详情）且可按类型过滤；测试覆盖

### E1 · 商品图片全链路（已完成 2026-10-14）
- **目标**：商品有主图，商户上架时可上传，两端可见（此前商品卡片只有文字封面）
- **改动范围**：files（`is_public` 公开图片 + `OptionalUser` 匿名读）、shop（`products.image_file_id`
  + `ProductPublic.image_url`）、`tests/conftest.py`（FakeMinio / PNG_BYTES 共享）、
  演示图 `scripts/make_seed_images.py` + `scripts/seed_assets/*.png` + `seed_shop.py` 补图；
  前端 `packages/api-client/src/files.ts`、console 商品页（上传 + 缩略图）、游客端列表 / 详情
- **接口**：`POST /api/v1/files`（multipart，新增 `public=true`：**仅图片**可设公开，其余 400）；
  `GET /api/v1/files/{id}` 改为**公开文件任何人可读**（私有文件仍：未登录 401、他人 404）；
  `POST /api/v1/shop/products` 新增 `image_file_id`（跨模块经 `files_service.require_owned` 校验归属）
- **要点**：图片地址由商品模型 `image_url` 属性推导（`/api/v1/files/{id}`），一处定义处处可用；
  演示图用 `uv run --with pillow python scripts/make_seed_images.py` 生成（Pillow 不进项目依赖，
  产物 PNG 已提交）；seed 幂等：已有图不重复上传，MinIO 不可用则跳过并提示
- **完成判据**：匿名可读公开图（<img> 直连）；上传非图片设公开 400；引用他人 / 不存在的文件 404；
  商户上架带图 → 两端展示；121 项 pytest 通过

### E2 · 控制台首页概览（已完成 2026-10-14）
- **目标**：控制台打开即见经营概览（此前直接落到商品页），商户与管理员各有自己的视图
- **改动范围**：新模块 `modules/dashboard/`（schemas / service / router，无表）；
  shop / users / cs repository 增加计数查询（状态分组计数、低库存、今日下单与成交额、排队数）；
  `app/api/v1/router.py` 挂载；前端 `packages/api-client/src/dashboard.ts`、
  console 新页 `pages/Dashboard.vue`（`/` 默认路由 + 菜单「🏠 概览」，登录后落此页）
- **接口**：`GET /api/v1/dashboard/summary`（merchant / enterprise / admin；游客 403）
- **要点**：一个接口按角色返回不同字段（未涉及的字段为 None），前端按角色渲染——
  admin：全平台商品 / 订单 + 用户总数 + 待审核 + 最近 5 条审计日志；
  商户：自己的商品 / 订单 + 库存预警（≤10）+ 今日下单 / 成交；两者都看客服排队数；
  跨模块数据一律经各模块 service（`shop_service.dashboard_counts` 等），聚合层不碰别人 repository
- **完成判据**：两角色字段正确且互不泄漏；游客 403；库存预警 / 今日统计按定义计数；4 项 pytest 覆盖

### E4 · 商户商品编辑（已完成 2026-10-14）
- **目标**：商户上架后能改价 / 改库存 / 改描述 / 换图，不必下架重上
- **接口**：`PUT /api/v1/shop/products/{id}`（merchant / enterprise，**仅归属商户本人**）
- **要点**：部分更新语义 —— 请求体字段全部可选，`exclude_unset` 只应用提交过的字段
  （未提交的保持不变）；`image_file_id: null` 显式表示**移除主图**；换图仍走
  `files_service.require_owned` 校验归属；状态（上 / 下架）不在此接口改，走原状态接口；
  空请求 400；改价 / 换图后 `cache.bump_version("shop:products")` 让公开列表立即生效
- **前端**：管理端商品页同一个对话框双模式（上架 / 编辑），编辑带出原值与主图预览，
  支持换图（重新上传）或移除；「编辑」按钮只对**自己的商品**显示（管理员看全平台列表时不出现）
- **完成判据**：部分更新只改提交字段；他人 403、不存在 404、游客 403；换图 / 移除图正确；
  公开列表价格立即更新；测试覆盖（`tests/test_shop.py::test_update_product_owner_only_and_partial`）

### E5 · 用户个人中心（已完成 2026-10-14）
- **目标**：用户可改昵称 / 改密码（此前只有 `/users/me` 查询）
- **接口**：`PUT /api/v1/users/me`（改昵称）；`POST /api/v1/auth/password`（改密码）
- **要点**：改密码的归属放在 **auth 模块**（密码是凭据域，且 users 不能反向依赖 auth，
  否则循环 import）：校验原密码（错误 401「原密码不正确」）→ 新旧相同 400 →
  `users_service.set_password` 更新哈希 → `revoke_all_for_user` **撤销该用户全部会话** →
  为当前端新开会话并返回新令牌对（当前端自动续期，其他设备需重新登录）；
  前端 401 刷新重放逻辑对 `/auth/*` 路径不生效，因此 401 不会造成刷新-重放循环
- **前端**：游客端新增「个人中心」页（账号信息 + 改昵称 + 改密码，入口在顶栏账号区）
  改昵称后同步刷新 auth store（顶栏昵称立即更新）；管理端顶栏加「修改密码」对话框
- **完成判据**：改昵称 / 改密码全通；旧刷新令牌失效、新令牌可刷新；旧密码不可再登录；
  新密码可登录；浏览器两端实测

### E6 · 预设路线运营后台（已完成 2026-10-14）
- **目标**：路线不再依赖 seed 脚本，管理员可在控制台增删改（此前只有只读接口）
- **接口**：`POST /travel/routes` 新建 / `PUT /travel/routes/{id}` 全量更新（含停靠点整体替换）
  / `DELETE /travel/routes/{id}` —— 均 **仅管理员**（`require_roles(ADMIN)`）
- **要点**：停靠点的 `position` 由服务端按数组顺序推导（同日计数），无需前端传；
  校验景点存在（404）与 day ≤ 天数（400）；路线与停靠点同一事务落库；
  变更后 `cache.bump_version("travel:routes")` 让公开列表 / 详情缓存立即失效；
  删除先删停靠点（PG 强制外键）
- **前端**：控制台新增「🗺️ 路线管理」（仅管理员菜单）：列表 + 新建 / 编辑对话框
  （停靠点行式编辑器：景点下拉 + 第几天 + 当日提示，可增删行）+ 删除二次确认
- **完成判据**：建 / 改 / 删全通且非管理员 403；停靠点回填与重排正确；公开列表即时反映；
  测试覆盖（`tests/test_travel.py::test_route_admin_crud`）；浏览器 UI 全流程实测

### E7 · 商品管理状态筛选（已完成 2026-10-14）
- **目标**：商户 / 管理员在商品管理页按「在售 / 已下架」筛选（此前只能翻列表）
- **接口**：`GET /api/v1/shop/merchant/products?status=on_sale|off_shelf`（非法值 400）
- **要点**：过滤下推到 repository 查询（分页 total 与筛选一致，不是前端过滤）；
  控制台商品页头部加状态下拉（清空即全部，切换时回到第 1 页）
- **完成判据**：三种查询结果互斥且与库内状态一致；测试覆盖（`tests/test_shop.py::test_merchant_products_status_filter`）

### E8 · 前端自动化测试（已完成 2026-10-14）
- **目标**：补上前端零测试的短板（此前只有后端 130 项 + 并发 e2e）
- **基建**：vitest 2 + happy-dom（各包声明依赖，走 pnpm 锁文件）；`pnpm -r test` / `make test-web`；
  CI 前端 job 增加「单元测试（vitest）」步骤（job 更名「前端测试 + 类型检查 + 构建」）
- **覆盖（37 项）**：
  - `packages/api-client`（9）：响应信封解包 / 非 0 code 抛 ApiError / 非 JSON 响应 /
    Authorization 注入 / **401 自动刷新重放**（含**并发单飞只刷新一次**、刷新失败清令牌、
    `/auth/*` 不触发刷新避免循环）/ FormData 上传不带 Content-Type
  - `packages/ui`（11）：QhButton（variant/size/disabled/点击）、QhPagination（页码信息、
    change 事件、边界禁用、total=0）、QhInput（v-model、属性透传）、QhTag / QhEmpty / QhCard
  - `apps/tourist`（17）：cart store（角标、未登录不请求、失败清零）、auth store（restore 静默 /
    login 后 displayName 回退 / register 不自动登录 / logout 清空 / fetchUser 抛错）、
    商城列表页组件测试（有图渲染 / 无图回退封面 / 空态 / 请求失败 / 价格缺货）
- **要点**：页面级用例用 `vi.mock('@qh/api-client')` + `@vue/test-utils`，RouterLink 用桩替换；
  这类用例是后续页面测试的模板（改一个页面加一个用例即可）
- **完成判据**：`pnpm -r test` 37 项全绿；CI 前端 job 通过

### E9 · 事务约定统一收口（cs / auth / users，已完成 2026-10-14）
- **约定**：repository **只 flush 不 commit**，事务边界统一由 service 控制
  （travel / b2b 已在 D1 统一，admin 的 create_log 已在 D2 改 flush；本次收口剩余三个模块）
- **改动范围**：`modules/users/`、`modules/auth/`、`modules/cs/` 的 repository 与 service
- **各模块要点**：
  - **users**：`create` / `save` 改 flush；注册、创建管理员、审核 / 启禁用、改昵称 / 改密码
    在 service 内提交（`set_password` 自带提交，跨模块改密码流程见 auth）
  - **auth**：`create_session` / `revoke_if_active` / `revoke_family` / `revoke_all_for_user` /
    `delete_stale` / `save` 全部改 flush；提交点集中在 service——登录、刷新、改密码、
    退出、清理任务；**刷新轮换「撤销旧会话 + 建立新会话」现在同一事务**（此前分两次提交），
    并发轮换仍由原子条件更新保证只有一个成功；重放处置与异常账号撤销各自立即提交
  - **cs**：7 处写操作改 flush；`create_session` / `send_message`（三条返回路径）/
    四个流转动作在 service 提交；**流转的审计日志改用 `record_action(commit=False)`，
    与状态变更同一事务**
- **验证**：130 项 pytest + 真 PG/Redis 并发 e2e 14 项全绿（含刷新令牌轮换 / 重放检测 /
  幂等下单等并发路径）；auth 会话安全用例覆盖轮换与重放
- **遗留**：无（admin 侧 create_log 已由 record_action 控制提交）

### E10 · 审计日志覆盖扩展（业务动作，已完成 2026-10-14）
- **目标**：除管理员操作与客服流转外，把**业务关键动作**也纳入审计（谁在什么时候动了什么）
- **新动作码与目标类型**：
  - `order.cancel`（actor = 买家，target_type=`order`）：取消订单（含订单号 / 金额 / 库存已回补）
  - `payment.callback`（actor = 管理员，target_type=`payment`）：模拟支付回调（接真实网关后 actor 可为空）
  - `route.create` / `route.update` / `route.delete`（actor = 管理员，target_type=`route`）：预设路线增删改
- **要点**：全部用 `record_action(..., commit=False)` **与业务变更同一事务**（E9 后 service 统一控制提交）；
  shop / travel 的 service 通过 `admin_service`（跨模块只走 service）写日志；
  路线维护的 actor 由路由的 `AdminUser` 注入 service（参数签名 `create_route(db, actor, ...)`）
- **前端**：管理端审计页与概览「最近操作」补 5 个新动作标签；目标类型筛选加 订单 / 支付单 / 预设路线
- **完成判据**：取消订单 / 支付回调 / 路线增删改均产生审计且可按目标类型过滤；
  测试覆盖（shop 审计用例 + travel 审计用例）；live 实测订单取消留痕

### E11 · C++ 继续下沉：路径总里程（已完成 2026-10-14）
- **目标**：路线 / 行程详情显示「全程约 X 公里」，把相邻点距离累加下沉到计算核心
- **改动范围**：`cpp_core/src/route.cpp`（新）+ 头文件 / 绑定 / CMakeLists；
  `app/core/compute.py`（`path_length_km` + Python 回退）；travel 详情载荷；
  前端 `types.ts`、路线详情页与行程详情页展示
- **接口契约**：`GET /travel/routes/{id}` 与行程详情新增 `total_distance_km`
  （**停靠点齐全且都有坐标**才给出，缺坐标返回 null——不猜假数据；保留 1 位小数，
  与景点列表 `distance_km` 口径一致）
- **要点**：C++ 侧 `path_length_km(points: [(lat, lng), ...])` 复用同文件里的 Haversine 累加；
  pybind11 经 `stl.h` 直接接收 `list[tuple[float, float]]`；少于两个点返回 0；
  **改 C++ 后必须停后端再 `make build-core`**（.pyd 被占用），且旧 .pyd 缺新函数时
  `compute._has_cpp` 自动回退 Python
- **完成判据**：C++ 与 Python 实现一致（含空 / 单点 / 多点边界）；路线与行程详情里程正确、
  缺坐标返回 null；`pnpm -r build` 与 135 项 pytest 全绿；浏览器两处展示确认
  （环线 231.8 公里 / 大环线 1141.9 公里）

### P1 · 承载能力（需求 4.3，公共层）
- **需求**：5000 同时在线查看 / 500 同时交易 / 100 同时 AI 搜索；超载排队、交易优先
- **依赖**：`uv add redis`（依赖走 uv）；Redis 已起
- **要点**：先做三件——① 登录 / 下单 / AI 接口的 Redis 限流；② 单机排队（超出并发返回"排队中"响应，交易接口优先放行）；③ 热点数据缓存（景点 / 商品列表）。压测脚本（Locust / k6）另起
- **完成判据**：限流与排队有测试；压测报告（本地）指标达到或说明差距

### P2 · 资质文件上传（公共层 + admin，需求 4.1）
- **要点**：MinIO 已起（docker-compose）；先做 `POST /api/v1/admin/uploads`（或独立 `files` 模块）返回可访问 URL，再让商户注册的 `license_file` 支持传入该 URL；权限：登录用户可传、仅自己可读
- **人工复核点**：文件类型 / 大小限制；路径不可穿越

### P3 · 部署（Nginx / TLS）
- **要点**：docker-compose 增加 nginx 反代前端与后端、限流（配合 P1）、HTTPS（自签或域名）；生产 .env 清单（密钥替换 `JWT_SECRET`、关闭 mock）

### A7 · 需求 4.2 自动登录策略层（挂起：**待需求方拍板**）
- 方案建议：设备指纹 + Refresh Token（记住我）——刷新令牌机制 (A5) 已就绪，本卡只加"策略层"
- 拍板前不要动 auth 的登录语义
