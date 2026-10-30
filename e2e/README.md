# 浏览器端 E2E（N6）

用真实浏览器跑三条主链路的冒烟测试。**与开发 / 演示环境完全隔离**：独立 SQLite 临时库、独立后端端口、前端跑构建产物。

## 前置

| 项 | 要求 |
|---|---|
| Node / pnpm | 见根目录 `AGENTS.md`（本目录是 pnpm workspace 成员，依赖走锁文件） |
| Python / uv | 同上（后端准备库与迁移用） |
| 浏览器 | **系统 Edge**（`channel: 'msedge'`），无需下载 Chromium |
| Docker | **不需要**——测试库是临时 SQLite，Redis / MinIO 自动降级 |

依赖安装（在 `frontend/` 下，一次即可）：`pnpm install`

## 一键运行

```bash
# 仓库根目录
make e2e-web
```

它做两件事：`pnpm -r build`（preview 需要 dist）→ `playwright test`。
也可以手动跑：

```bash
cd frontend && pnpm -r build          # preview 需要 dist
cd frontend && pnpm --filter @qh/e2e test:e2e                          # 全部三条链路
cd frontend && pnpm --filter @qh/e2e exec playwright test tests/order-flow.spec.ts  # 单条
cd frontend && pnpm --filter @qh/e2e exec playwright test --ui         # 交互式调试（可选）
```

> 依赖由 `frontend/pnpm-lock.yaml` 统一管理（e2e 是 pnpm workspace 成员），
> 不要在 `e2e/` 目录里单独 `pnpm install`——那会生成第二份锁文件。

运行时会自动：

1. **重建测试库**（`e2e/.tmp/e2e.db`）+ 跑迁移 + 导入种子（管理员 / 商户 / 两个商品 / 5 个景点 / 4 条路线，见 `prepare_db.py`）；
2. 起三个服务：后端 `8100`、游客端 `5273`、控制台 `5274`（`vite preview` 跑构建产物，`/api` 代理指向 `8100`）；
3. 跑完自动关掉三个服务，失败时在 `e2e/test-results/` 留截图与 trace。

## 三条链路

| 文件 | 链路 | 检查点 |
|---|---|---|
| `tests/order-flow.spec.ts` | 下单全链路 | 注册 → 地址簿 → 商城直购（**收货信息自动带出默认地址**）→ 支付单 → 管理员模拟回调 → 商户**发货**（运单号）→**标记签收**→ 买家**确认收货** → 申请**售后** → 商户受理 / 完成 → 买家看到「已解决」 |
| `tests/travel-flow.spec.ts` | 旅行链路 | 景点列表 → 景点详情 → 精选路线详情 →**套用为我的行程** → 编辑停靠点（增）→ 保存 → 我的行程列表可见 |
| `tests/cs-flow.spec.ts` | 客服链路 | 游客发起会话 → **AI 应答** → 转人工（排队）→ 商户工作台**接入**并回复 → 游客端（5 秒轮询）看到人工回复与「人工客服接待中」 |

## 固定测试账号（仅存在于临时库）

| 角色 | 手机号 | 密码 |
|---|---|---|
| 管理员 | `13800000000` | `admin123456` |
| 商户 | `13800000088` | `Demo123456` |

游客账号由用例即时注册（13 开头随机号）。

## 失败排查

```bash
cd frontend && pnpm --filter @qh/e2e exec playwright show-trace ../e2e/test-results/<用例目录>/trace.zip
cd frontend && pnpm --filter @qh/e2e run report       # HTML 报告
```

## 清理

```bash
rm -rf e2e/.tmp e2e/test-results e2e/playwright-report
```

（`.gitignore` 已忽略这三项；测试库每次运行前都会重建，不会污染开发库 `dev.db` 与演示库。）

## 说明与边界

- 端口 8100 / 5273 / 5274 固定占用；与本机开发服务（8000 / 5173 / 5174）互不影响，可同时运行。
- 用例串行执行（`workers: 1`）：三条链路共用同一个测试库。
- 尚未接入 CI（按计划先本地跑稳定；需要时再加 `workflow_dispatch` 的手动触发任务）。
- Element Plus 的弹层（`el-dialog` / `el-message-box`）在真实浏览器里正常渲染，因此这里能覆盖到 N5 单测覆盖不到的弹窗交互。
