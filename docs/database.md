# 数据模型说明

> 本文档描述各模块归属的数据表。**表由所属模块独占**，其他模块不得直接读写，
> 只能通过该模块的 `service` 访问（见 README 的模块边界约定）。

## 已实现

### users（模块：users）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增主键 |
| phone | varchar(20) UK | 手机号，登录账号，唯一索引 |
| password_hash | varchar(128) | bcrypt 哈希，不存明文 |
| role | varchar(20) | `tourist` / `merchant` / `enterprise`，索引 |
| status | varchar(20) | `active` / `pending_review` / `rejected` / `disabled` |
| nickname | varchar(64) | 昵称（游客）或企业 / 商户名称 |
| license_no | varchar(64) | 营业执照号（商户 / 企业） |
| license_file | varchar(255) | 资质文件地址（商户 / 企业） |
| created_at | timestamptz | 创建时间 |

**业务约束**
- 游客注册后 `status = active`，可直接登录。
- 商户 / 企业注册必须提供 `license_no`，注册后 `status = pending_review`，审核通过前不能登录。

### sessions（模块：auth）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增主键 |
| user_id | int idx | 所属用户 id |
| token_hash | varchar(64) UK | 刷新令牌的 SHA-256 哈希（不存明文） |
| user_agent | varchar(255) | 登录设备信息（可空） |
| created_at | timestamptz | 会话创建时间 |
| expires_at | timestamptz idx | 刷新令牌过期时间（当前 30 天） |
| revoked_at | timestamptz | 撤销时间；非空即失效（轮换 / 退出登录 / 账号异常） |

**业务约束**
- 一次登录一条，同一用户可多设备并存；refresh 轮换（旧行撤销 + 新增一行）。
- 访问令牌短时效（30 分钟，见 `core/config.py`），过期后用刷新令牌换新令牌对。

### attractions / tickets（模块：travel）

| 表.字段 | 类型 | 说明 |
|---|---|---|
| attractions.id | int PK | 自增主键 |
| attractions.name | varchar(128) | 景点名称 |
| attractions.city | varchar(64) idx | 所在城市 / 州 |
| attractions.description | text | 景点介绍 |
| attractions.latitude / longitude | float | 地理坐标（经纬度为源数据） |
| attractions.geom | geometry(Point,4326) | **PostGIS 几何列**：由迁移创建并回填，GIST 索引支撑 bbox 点位查询；不映射 ORM，新增景点后需跑 `repository.backfill_geom`（seed 脚本已内置） |
| attractions.cover_image | varchar(255) | 封面图地址（可空） |
| attractions.created_at | timestamptz | 创建时间 |
| tickets.id | int PK | 自增主键 |
| tickets.attraction_id | int idx FK | 所属景点 |
| tickets.name | varchar(64) | 票种名称 |
| tickets.price | numeric(10,2) | 价格 |
| tickets.description | varchar(255) | 说明（可空） |
| tickets.created_at | timestamptz | 创建时间 |

**业务约束**
- 景点列表与详情为公开接口（无需登录）；演示数据用 `backend/scripts/seed_travel.py` 写入（幂等）。

### itineraries / itinerary_stops（模块：travel）

| 表.字段 | 类型 | 说明 |
|---|---|---|
| itineraries.id | int PK | 自增主键 |
| itineraries.user_id | int idx | 行程归属游客 |
| itineraries.title | varchar(128) | 行程标题 |
| itineraries.days | int | 天数 |
| itineraries.budget | numeric(10,2) | 预算（可空） |
| itineraries.preferences / fitness | text / varchar(64) | 偏好与身体条件（自由文本） |
| itineraries.risk_notes | text | 风险提示（模型生成，失败有兜底文案） |
| itineraries.created_at / updated_at | timestamptz | 创建 / 更新 |
| itinerary_stops.id | int PK | 自增主键 |
| itinerary_stops.itinerary_id | int idx FK | 所属行程 |
| itinerary_stops.attraction_id | int idx FK | 景点 |
| itinerary_stops.day / position | int | 第几天 / 同日内顺序 |
| itinerary_stops.note | varchar(255) | 备注（可空） |

**业务约束**
- 行程仅归属游客与管理员可见；停靠点用全量替换接口（PUT）一次完成增 / 删 / 排序。
- mock 阶段生成 = 确定性选点排程（偏好优先、每天 2 个）+ 模型生成风险提示；
  接真实模型后可改为模型直接产出结构化行程（service 内一处）。

### ai_conversations / ai_messages（模块：ai）

| 表.字段 | 类型 | 说明 |
|---|---|---|
| ai_conversations.id | int PK | 自增主键 |
| ai_conversations.user_id | int idx | 会话归属用户 |
| ai_conversations.title | varchar(128) | 标题（取首个提问前 30 字） |
| ai_conversations.created_at / updated_at | timestamptz | 创建 / 最后活跃 |
| ai_messages.id | int PK | 自增主键 |
| ai_messages.conversation_id | int idx | 所属会话 |
| ai_messages.role | varchar(20) | `user` / `assistant`（与 OpenAI 协议一致） |
| ai_messages.content | text | 消息内容 |
| ai_messages.created_at | timestamptz | 时间 |

**业务约束**
- prompt 组装：系统提示 + **最简 RAG**（本地知识库按关键词命中排序取前 3 条）
  + 联网搜索适配器（提问含「最新/现在/天气」等词时触发，当前 mock 实现）
  + 最近 6 条对话历史；模型统一走 `app/core/llm.py`。
- `/ai/ask` 常规返回；`/ai/ask/stream` 为 SSE（mock 阶段一次性生成后分块吐出，
  接真实流式模型时改为逐 token 转发）；会话仅归属用户可见。

### weather_snapshots / gear_recommendations（模块：gear）

| 表.字段 | 类型 | 说明 |
|---|---|---|
| weather_snapshots.id | int PK | 自增主键 |
| weather_snapshots.city | varchar(64) idx | 城市 / 州 |
| weather_snapshots.snapshot_date | date idx | 日期（与 city 联合唯一，采集幂等） |
| weather_snapshots.temperature_c / soil_moisture_pct | numeric(4,1) | 气温 / 土壤湿度 |
| weather_snapshots.altitude_m | int | 海拔（按州市基准） |
| weather_snapshots.pressure_hpa | numeric(6,1) | 气压（按海拔按国际标准大气近似） |
| weather_snapshots.source | varchar(32) | 数据来源（当前为 `mock` 模拟源） |
| gear_recommendations.id | int PK | 自增主键 |
| gear_recommendations.snapshot_id | int UK | 关联快照（一个快照只生成一次） |
| gear_recommendations.items | text | 建议条目（JSON 数组文本） |
| gear_recommendations.notes | text | 模型生成的一句话提醒（失败有兜底文案） |

**业务约束**
- 采集：Celery Beat 每天 06:00（`app/worker.py`）或手动 `scripts/collect_weather.py`；
  采集各州市未来 7 日快照，已存在的 (city, date) 跳过。
- 接真实气象源时只需替换 `gear/service.py` 的模拟函数并调整 `source` 字段。

### shop 交易闭环（模块：shop）

| 表 | 关键字段 |
|---|---|
| `products` | merchant_id / name / description / price(Numeric 10,2) / stock / status（`on_sale`/`off_shelf`） |
| `orders` | user_id / merchant_id（一单只含一个商户）/ amount / status（`created`→`paid`）/ **idem_key**（幂等键，`(user_id, idem_key)` 唯一）/ paid_at |
| `order_items` | order_id / product_id / product_name 与 unit_price **快照** / quantity / amount |
| `cart_items` | user_id + product_id 唯一（每人一辆车；未单独建 carts 表，按需再拆） |
| `inventory` | product_id / change(±) / reason（`order`/`restock`）/ ref_id（订单 id）——库存流水 |
| `payments` | order_id / user_id / amount / channel / status（`created`/`success`/`failed`）/ trade_no（第三方单号）/ paid_at |
| `favorites` | user_id + product_id 唯一（收藏，重复提交幂等）；收藏数参与首页推荐的兴趣打分 |
| `product_views` | user_id + product_id 唯一（浏览历史，同一商品一条）/ view_count（重复浏览累加）/ viewed_at；热度按**去重用户数**统计（单账号刷详情不能刷榜） |

**业务约束**
- 下单（直购与购物车结算）：**Redis 预扣闸门（可降级）+ 数据库条件更新（权威）** 双保险防超卖；
  扣减 / 落单 / 清空购物车在同一事务；下单成功后 Redis 与数据库库存同步（键带 1 小时 TTL 防漂移）。
- **幂等**：请求带 `idem_key` 时重复提交返回首次订单（并发由唯一约束兜底）。
- 金额一律 Decimal（ROUND_HALF_UP 到分）；单笔上限 99999999.99。
- 购物车结算一次只能含同一商户商品；支付走第三方、平台不做资金池——
  当前为占位回调（仅管理员可触发），接真实网关后改为验签回调。

### cs_sessions / cs_messages（模块：cs）

| 表.字段 | 类型 | 说明 |
|---|---|---|
| cs_sessions.id | int PK | 自增主键 |
| cs_sessions.user_id | int idx | 会话发起人 |
| cs_sessions.status | varchar(20) idx | `ai` 智能客服接待 / `queued` 排队转人工 / `human` 人工服务中 / `closed` 已结束 |
| cs_sessions.agent_id | int | 接入的人工客服用户 id（可空） |
| cs_sessions.created_at / updated_at / queued_at / closed_at | timestamptz | 创建 / 活跃 / 进入人工队列 / 结束时间 |
| cs_messages.id | int PK | 自增主键 |
| cs_messages.session_id | int idx | 所属会话 |
| cs_messages.sender_type | varchar(20) | `user` / `ai` / `agent` / `system` |
| cs_messages.sender_id | int | user / agent 为对应用户 id（可空） |
| cs_messages.content | text | 消息内容 |
| cs_messages.created_at | timestamptz | 时间 |

**业务约束**
- AI 接待（`ai`）状态下用户发言自动应答（统一入口 `app/core/llm.py`）；应答失败自动转人工。
- 商家（商户 / 企业角色）从队列接入会话后人工回复；发起人可随时结束会话。
- 状态迁移（转人工 / 接入 / 释放 / 结束）均为**原子条件更新**，并发下只有一方成功；
  队列按 `queued_at` 先到先服务（排队期间发消息不影响顺序）。
- 会话队列为**平台级**（任一商户 / 企业可接入任意用户的会话）；用户与商家的绑定
  范围待需求明确后再细分（商家客服按店铺路由）。

### audit_logs（模块：admin）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 自增主键 |
| actor_id | int idx | 操作人（管理员）的用户 id |
| action | varchar(32) idx | 动作码：`review.approve` / `review.reject` / `user.disable` / `user.enable` |
| target_type | varchar(32) | 目标类型，当前仅 `user` |
| target_id | int idx | 目标对象 id |
| detail | varchar(255) | 可读描述（如"手机号 xx 资质审核通过"） |
| created_at | timestamptz idx | 创建时间 |

**业务约束**
- 仅管理员操作触发：审核通过 / 驳回、用户启用 / 禁用四类动作各记一条。
- 只追加、不修改、不删除。

### b2b_supplies / b2b_demands / b2b_matches（模块：b2b）

| 表 | 关键字段 |
|---|---|
| `b2b_supplies` | user_id（发布者）/ title / category idx / region idx / quantity(Numeric 12,2) / unit / price_expect（参考价，可空）/ description / status（`open`/`closed`） |
| `b2b_demands` | 同上结构（需求方发布） |
| `b2b_matches` | demand_id / supply_id（联合唯一）/ score（0-100）——规则匹配结果 |

**业务约束**
- **平台只提供信息服务、不做交易**：以上三张表不含任何订单 / 支付字段。
- 发布需商户 / 企业角色；浏览与详情公开（仅展示 `open` 状态）。
- 规则匹配（确定性）：品类必须一致；基础 60 分 + 地区一致 20 分 + 数量满足 20 分；
  只对需求发布者开放，重复匹配为全量替换（先删后插）。

## 规划中（尚未实现）

原计划表已全部落地。按需再做的候选：平台预设路线（travel 的 `routes` / `route_stops`）。

## 迁移规范

1. 修改或新增模型后，必须生成迁移并提交：
   ```bash
   cd backend
   uv run alembic revision --autogenerate -m "描述"
   uv run alembic upgrade head
   ```
2. 新模型要在 `backend/app/db/models_registry.py` 里加一行 import，否则自动生成检测不到。
3. **不要手改已经提交的迁移文件**；需要调整就再生成一个新迁移。
4. 迁移文件会进版本控制，多人协作时先拉取再生成，避免出现分叉的两条迁移链。
