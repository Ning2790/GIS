/**
 * 答辩 PPT 构建脚本（pptxgenjs）。
 * 用法：node build.js
 * 输出：D:/系统文件/桌面/xiangmu/docs/答辩PPT.pptx
 */
const pptxgen = require('pptxgenjs');

// ---- 调色板（青海湖蓝 + 高原暖黄），所有幻灯片只引用这些常量 ----
const DARK = '0B2E38';        // 封面 / 结尾（深湖蓝）
const BG = 'FFFFFF';
const PRIMARY = '0E5A6B';     // 主色（湖蓝）
const PRIMARY_SOFT = 'E6F1F4';// 主色浅底（tint band / 卡片）
const ACCENT = 'D97706';      // 强调色（高原暖黄，仅用于最关键元素）
const TEXT = '1F2937';
const MUTED = '64748B';
const HAIRLINE = 'E2E8F0';
const FONT = '微软雅黑';

const SHOT = 'D:/系统文件/桌面/xiangmu/docs/screenshots';
const OUT = 'D:/系统文件/桌面/xiangmu/docs/答辩PPT.pptx';

const W = 13.33, H = 7.5, M = 0.55;

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE';
pres.author = '青海旅游 + 农产品平台团队';
pres.title = '青海旅游 + 农产品平台 · 答辩';

const shadow = () => ({ type: 'outer', color: '0F172A', blur: 9, offset: 3, angle: 90, opacity: 0.12 });

/** 带白色圆角底 + 细边框 + 轻阴影的截图卡片（本套幻灯片的统一视觉母题）。 */
function shot(slide, file, x, y, w, h) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.06, fill: { color: BG }, line: { color: HAIRLINE, width: 1 }, shadow: shadow(),
  });
  slide.addImage({ path: `${SHOT}/${file}`, x: x + 0.04, y: y + 0.04, w: w - 0.08, h: h - 0.08, sizing: { type: 'cover', w: w - 0.08, h: h - 0.08 } });
}

/** 内容页标题（无下划线、无装饰条）。 */
function head(slide, title, sub) {
  slide.addText(title, { x: M, y: 0.42, w: W - 2 * M, h: 0.6, fontFace: FONT, fontSize: 30, bold: true, color: PRIMARY, margin: 0 });
  if (sub) slide.addText(sub, { x: M, y: 1.02, w: W - 2 * M, h: 0.34, fontFace: FONT, fontSize: 13.5, color: MUTED, margin: 0 });
}

/** 行列表（发丝线分隔，无容器）。 */
function rows(slide, items, x, y, w, rowH) {
  items.forEach((it, i) => {
    const top = y + i * rowH;
    slide.addText(it.n, { x, y: top, w: 0.72, h: rowH - 0.12, fontFace: FONT, fontSize: 22, bold: true, color: ACCENT, margin: 0, valign: 'middle' });
    slide.addText(
      [
        { text: it.t, options: { bold: true, color: TEXT, breakLine: true } },
        { text: it.d, options: { color: MUTED, fontSize: 13 } },
      ],
      { x: x + 0.8, y: top, w: w - 0.8, h: rowH - 0.12, fontFace: FONT, fontSize: 15.5, margin: 0, valign: 'middle', paraSpaceAfter: 0 },
    );
    if (i < items.length - 1) slide.addShape(pres.shapes.LINE, { x, y: top + rowH - 0.1, w, h: 0, line: { color: HAIRLINE, width: 1 } });
  });
}

/** 大数字卡（数字 60pt + 标签）。 */
function stat(slide, x, y, w, h, value, label, accent, valueSize) {
  slide.addText(value, { x, y, w, h: h * 0.62, fontFace: FONT, fontSize: valueSize || 40, bold: true, color: accent ? ACCENT : PRIMARY, align: 'center', valign: 'bottom', margin: 0 });
  slide.addText(label, { x, y: y + h * 0.62, w, h: h * 0.34, fontFace: FONT, fontSize: 13, color: MUTED, align: 'center', valign: 'top', margin: 0 });
}

// ============================== 1 封面 ==============================
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText('青海旅游 + 农产品平台', { x: M, y: 2.05, w: 6.6, h: 1.0, fontFace: FONT, fontSize: 40, bold: true, color: 'FFFFFF', margin: 0 });
  s.addText('智能行程规划 · 行前装备建议 · 特产直购 · 供需撮合', { x: M, y: 3.1, w: 6.6, h: 0.5, fontFace: FONT, fontSize: 17, color: 'A8CBD4', margin: 0 });
  s.addShape(pres.shapes.LINE, { x: M, y: 3.85, w: 2.2, h: 0, line: { color: ACCENT, width: 2 } });
  s.addText(
    [
      { text: 'FastAPI + Vue 3 + PostgreSQL/PostGIS + Redis + MinIO', options: { breakLine: true } },
      { text: 'C++ 计算核心（pybind11）· 5 人团队：3 后端 + 2 前端', options: { breakLine: true } },
      { text: '答辩演示 · 2026 年 10 月', options: {} },
    ],
    { x: M, y: 4.15, w: 6.6, h: 1.1, fontFace: FONT, fontSize: 13.5, color: '8FB3BD', lineSpacingMultiple: 1.35, margin: 0 },
  );
  shot(s, '03-map.png', 7.45, 1.75, 5.35, 4.0);
}

// ============================== 2 背景与问题 ==============================
{
  const s = pres.addSlide();
  head(s, '要解决的四类问题', '平台围绕「游客体验」与「农产品出村」两条主线设计');
  rows(s, [
    { n: '01', t: '游客不了解青海旅游资源', d: '景点库 / 地图三图与点位 / 精选路线 / AI 问答（本地知识库检索）' },
    { n: '02', t: '农户农产品难卖给企业，企业难找优质原料', d: 'B2B 供需撮合：持资质发布、公开浏览、规则匹配（平台只做信息服务）' },
    { n: '03', t: '农户与企业的产品难直接卖给游客', d: 'B2C 商城闭环：上架（带主图）→ 下单 → 支付 → 发货签收 → 售后，防超卖、防重复下单' },
    { n: '04', t: '行前不知道带什么、有哪些高原风险', d: '装备建议（气温 / 海拔 / 气压 / 土壤湿度）+ 行程风险提示' },
  ], M + 0.1, 1.75, W - 2 * M - 0.2, 1.28);
}

// ============================== 3 整体方案（架构图） ==============================
{
  const s = pres.addSlide();
  head(s, '整体方案：模块化单体 + 双前端', '接口契约先行（OpenAPI）；跨模块只走 service；统一响应信封 {code, msg, data}');
  const box = (x, y, w, h, text, fill, color, size) =>
    s.addText(text, { x, y, w, h, fontFace: FONT, fontSize: size || 12, bold: false, color: color || TEXT, fill: { color: fill }, line: { color: HAIRLINE, width: 1 }, align: 'center', valign: 'middle', margin: 0.03 });
  const arrow = (x, y, w) => s.addShape(pres.shapes.LINE, { x, y, w, h: 0, line: { color: PRIMARY, width: 1.5, endArrowType: 'triangle' } });

  box(0.7, 1.65, 2.8, 1.0, '游客端（Vue 3）\n行程 / 地图 / 商城 / 客服 / AI', PRIMARY_SOFT, PRIMARY, 11.5);
  box(0.7, 2.95, 2.8, 1.0, '管理控制台（Vue 3 + Element Plus）\n商户 / 管理员按角色分流', PRIMARY_SOFT, PRIMARY, 11.5);
  arrow(3.6, 2.15, 0.55); arrow(3.6, 3.45, 0.55);
  box(4.25, 2.1, 2.55, 1.4, 'Nginx 网关\nTLS · 限流\n静态资源 · 反向代理', 'F1F5F9', TEXT, 11);
  arrow(6.9, 2.8, 0.5);
  box(7.5, 1.55, 3.5, 2.6, 'FastAPI 后端 · 12 个业务模块\nauth / users / travel / map / gear\nshop / b2b / ai / cs / admin\nfiles / dashboard\n（仓储层只 flush，事务由 service 统一控制）', 'FFFFFF', TEXT, 11);
  arrow(11.1, 2.1, 0.5);
  box(11.7, 1.55, 1.05, 2.6, 'PostgreSQL\n+PostGIS\n\nRedis\n\nMinIO\n\nCelery\nBeat', 'F1F5F9', TEXT, 10);
  box(7.5, 4.55, 3.5, 0.95, 'C++ 计算核心 qh_core（pybind11）\n距离 / 推荐打分 / 行程选点 / 路径里程\n未编译自动回退 Python', PRIMARY_SOFT, PRIMARY, 10.5);
  s.addShape(pres.shapes.LINE, { x: 9.25, y: 4.2, w: 0, h: 0.33, line: { color: PRIMARY, width: 1.5, dashType: 'dash' } });
  s.addText('承载设计：限流（按 IP / 用户）+ 排队闸门（交易优先，容量与连接池对齐）+ 热点缓存 + 多实例（least_conn）+ 运行指标与请求追踪', { x: M, y: 5.85, w: W - 2 * M, h: 0.4, fontFace: FONT, fontSize: 13, color: MUTED, margin: 0 });
  s.addText('工程质量：236 项后端单测（覆盖率 93.7%）+ 14 项并发 e2e + 81 项前端单测 + 3 条浏览器 E2E 冒烟，CI 三层全绿', { x: M, y: 6.3, w: W - 2 * M, h: 0.4, fontFace: FONT, fontSize: 13, color: MUTED, margin: 0 });
}

// ============================== 4 游客端 · 行程规划 ==============================
{
  const s = pres.addSlide();
  head(s, '游客端 · 智能行程与精选路线', 'AI 生成 + 平台精选路线一键套用，停靠点随时增删调整');
  shot(s, '05-route-detail.png', 6.6, 1.6, 6.2, 5.3);
  const items = [
    { t: 'AI 生成个性化行程', d: '按天数 / 预算 / 偏好 / 体力选点排程，附高原风险提示（模型不可用有兜底）' },
    { t: '精选路线一键套用', d: '平台维护 4 条经典线路，复制为个人行程后自由增删，不影响原路线' },
    { t: '全程里程由计算核心给出', d: '停靠点坐标在 C++ 中累加（本路线 1141.9 公里），未编译环境自动回退 Python' },
  ];
  rows(s, items, M + 0.1, 2.2, 5.7, 1.4);
}

// ============================== 5 游客端 · 地图 / 装备 / AI ==============================
{
  const s = pres.addSlide();
  head(s, '游客端 · 地图导航、行前装备与 AI 问答', '卫星 / 行政 / 地形三图与点位联动；装备建议结合实时环境数据');
  shot(s, '03-map.png', 0.55, 1.7, 4.0, 4.15);
  shot(s, '07-gear.png', 4.72, 1.7, 4.0, 4.15);
  shot(s, '23-ai-sources.png', 8.89, 1.7, 4.0, 4.15);
  const caps = [
    '地图三图切换 + 视野拉点（PostGIS 空间索引）',
    '装备清单：气温 / 海拔 / 气压 / 土壤湿度（真实气象源 + 断网回退）',
    'AI 问答：SSE 流式 + 向量检索（命中显示「参考平台知识」卡片）',
  ];
  caps.forEach((c, i) => s.addText(c, { x: 0.55 + i * 4.17, y: 6.0, w: 4.0, h: 0.9, fontFace: FONT, fontSize: 12.5, color: MUTED, align: 'left', margin: 0 }));
}

// ============================== 6 游客端 · 商城闭环 ==============================
{
  const s = pres.addSlide();
  head(s, '游客端 · 商城闭环：下单 → 履约 → 售后', '交易安全由并发设计保证：不超卖、不重复下单、库存回补可追溯');
  shot(s, '09-products.png', 0.55, 1.7, 5.7, 3.5);
  shot(s, '22-aftersales-tourist.png', 0.55, 5.35, 5.7, 1.6);
  const items = [
    { t: '商品主图', d: '受控上传 + 公开图片机制：匿名可读，资质类私有文件仍严格隔离' },
    { t: '幂等下单 + 取消', d: '幂等键防重复（并发只生成一笔订单）；取消为原子翻转、并发只生效一次，库存同事务回补' },
    { t: '防超卖双保险', d: 'Redis 预扣闸门 + 数据库条件更新，Redis 故障自动降级不阻断交易' },
    { t: '履约与售后单', d: '收货信息随订单快照（含地址簿）→ 发货签收 → 签收 7 天自动确认；售后单：申请 → 受理 → 完成 / 拒绝 + 双方留言' },
  ];
  rows(s, items, 6.55, 1.9, 6.25, 1.24);
}

// ============================== 7 管理端 · 经营看板 ==============================
{
  const s = pres.addSlide();
  head(s, '管理端 · 经营看板（按角色聚合）', '商户看自己的经营数据；管理员看全平台、待办与运行指标');
  shot(s, '14-dashboard.png', 0.55, 1.6, 8.2, 5.3);
  const items = [
    { t: '今日下单 / 成交', d: '成交额按「已支付且当日支付」口径统计' },
    { t: '库存预警', d: '在售商品库存 ≤ 10 自动标黄提示' },
    { t: '待审核与客服排队', d: '待办直达对应页面（资质审核 / 客服工作台）' },
    { t: '最近操作', d: '订单取消、支付回调、客服流转全程留痕' },
    { t: '运行指标（管理员）', d: '请求量 / P95 延迟 / 限流与排队拒绝 / 在途与容量，与 /metrics 同源' },
  ];
  rows(s, items, 9.0, 1.85, 3.8, 1.05);
}

// ============================== 8 管理端 · 运营管理页 ==============================
{
  const s = pres.addSlide();
  head(s, '管理端 · 六类运营管理页', '商品 / 履约 / 售后 / 路线 / 资质 / 客服，覆盖日常运营全流程；另有设备管理与审计日志');
  const shots = [
    ['19-products-merchant.png', '商品管理：主图、编辑（部分更新）、上下架、状态筛选'],
    ['15-orders.png', '订单与履约：发货（承运商 + 运单号）、标记签收、模拟支付回调'],
    ['21-aftersales-console.png', '售后管理：受理 / 完成 / 拒绝 + 与买家留言'],
    ['16-routes-manage.png', '路线管理：运营后台增删改 + 停靠点编辑器'],
    ['17-reviews.png', '资质审核：通过 / 驳回，审核前不可登录'],
    ['20-cs-workbench.png', '客服工作台：人工队列原子抢占接入'],
  ];
  shots.forEach(([file, cap], i) => {
    const x = 0.55 + (i % 3) * 4.12;
    const y = 1.62 + Math.floor(i / 3) * 2.72;
    shot(s, file, x, y, 3.88, 2.0);
    s.addText(cap, { x, y: y + 2.02, w: 3.88, h: 0.55, fontFace: FONT, fontSize: 10.5, color: MUTED, margin: 0 });
  });
}

// ============================== 9 技术亮点 · 并发与承载 ==============================
{
  const s = pres.addSlide();
  head(s, '技术亮点（一）· 并发正确性与承载能力', '承载按需求 4.3 三档实测（多实例 + 压测脚本可复现），并发用例跑在真实 PostgreSQL + Redis 上');
  s.addChart(pres.charts.BAR, [
    { name: '500 并发纯读（同口径）', labels: ['单实例', '双实例'], values: [539, 824] },
  ], {
    x: 0.55, y: 1.75, w: 7.3, h: 4.3, barDir: 'col', chartColors: [PRIMARY, ACCENT],
    showValue: true, dataLabelPosition: 'outEnd', dataLabelColor: TEXT, dataLabelFontFace: FONT, dataLabelFontSize: 13,
    showLegend: false, showTitle: false,
    catAxisLabelColor: MUTED, catAxisLabelFontFace: FONT, valAxisLabelColor: MUTED, valAxisLabelFontFace: FONT,
    valGridLine: { color: HAIRLINE, size: 0.5 }, catGridLine: { style: 'none' },
    chartArea: { fill: { color: BG } },
  });
  s.addText('放行吞吐（req/s）· 双实例 1.53×（客户端受限的下限，非容量上限）', { x: 0.75, y: 6.05, w: 6.6, h: 0.4, fontFace: FONT, fontSize: 11.5, color: MUTED, margin: 0 });
  stat(s, 8.3, 1.8, 2.2, 1.45, '1189', '读档 req/s（500 并发，P95 410ms）');
  stat(s, 10.6, 1.8, 2.2, 1.45, '81 单/s', '交易档（200 并发，目标 17–25）');
  stat(s, 8.3, 3.5, 2.2, 1.45, '5.4 次/s', 'AI 档 100 并发（mock）');
  stat(s, 10.6, 3.5, 2.2, 1.45, '115→0', '连接池超时（容量对齐）', true, 30);
  s.addText('容量与故障语义：闸门先拦（交易 50 / 认证 20 / 查看 200，实测在途安全值）· 库不可达 3 秒内回 503（改前实测挂 253 秒）· 提交后失败回 500 且不诱导重试 · least_conn 消除单台 503 集中（858 → 0）', { x: 0.55, y: 6.55, w: W - 2 * M, h: 0.6, fontFace: FONT, fontSize: 11.5, color: MUTED, margin: 0 });
  s.addText('Source: docs/压测报告.md（三档 + 双实例同口径对照 + 网关限流档 + 闸门与连接池容量对齐）', { x: 0.55, y: 7.05, w: 8, h: 0.35, fontFace: FONT, fontSize: 11, color: MUTED, margin: 0 });
}

// ============================== 10 技术亮点 · 计算核心与工程质量 ==============================
{
  const s = pres.addSlide();
  head(s, '技术亮点（二）· C++ 计算核心与工程质量', '算力核心用 C++（需求 5.1），工程质量用测试与 CI 兜底');
  s.addText('qh_core（pybind11 暴露）', { x: 0.75, y: 1.8, w: 4.2, h: 0.4, fontFace: FONT, fontSize: 15, bold: true, color: PRIMARY, margin: 0 });
  const fns = ['haversine_km — 大圆距离', 'distance_score — 距离推荐打分', 'planning_score — 行程选点打分', 'path_length_km — 路径总里程'];
  fns.forEach((f, i) => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.75, y: 2.35 + i * 0.68, w: 5.2, h: 0.56, rectRadius: 0.05, fill: { color: PRIMARY_SOFT }, line: { color: PRIMARY_SOFT } });
    s.addText(f, { x: 0.95, y: 2.35 + i * 0.68, w: 4.9, h: 0.56, fontFace: FONT, fontSize: 12.5, color: TEXT, valign: 'middle', margin: 0 });
  });
  s.addText('Python 回退：未编译 / 扩展过旧时按函数级探测自动回退，两套实现有一致性测试（CI 无需编译器）', { x: 0.75, y: 5.25, w: 5.4, h: 0.8, fontFace: FONT, fontSize: 12, color: MUTED, margin: 0 });
  stat(s, 6.9, 1.95, 2.9, 1.5, '236', '后端单元测试（覆盖率 93.7%）');
  stat(s, 10.0, 1.95, 2.9, 1.5, '81', '前端单元测试（vitest）');
  stat(s, 6.9, 3.65, 2.9, 1.5, '14 + 3', '并发 e2e（真 PG + Redis）' + String.fromCharCode(10) + '+ 浏览器 E2E 冒烟');
  stat(s, 10.0, 3.65, 2.9, 1.5, '3 层', 'CI：lint / 测试（覆盖率门禁 + 契约校验）/ 构建', true);
  s.addText('另有：事务约定全仓统一（仓储只 flush）· 审计留痕 · 安全加固（令牌轮换 / 重放检测 / 限流）· 可观测性（/metrics + X-Request-ID 请求追踪 + 慢请求告警）· 容器化部署（Dockerfile + compose full）', { x: 0.55, y: 5.85, w: W - 2 * M, h: 0.75, fontFace: FONT, fontSize: 12, color: MUTED, margin: 0 });
}

// ============================== 11 团队协作 ==============================
{
  const s = pres.addSlide();
  head(s, '团队协作：5 人分工 + GitHub 流程', '需求 5.2 / 5.3 / 5.4：仓库协作、环境一致、接口统一');
  const teams = [
    ['后端 A', 'auth / users / cs / admin', '登录会话、资质审核、客服与审计'],
    ['后端 B', 'travel / map / gear / ai / cpp_core', '行程与地图、装备建议、计算核心'],
    ['后端 C', 'shop / b2b', '商城交易闭环、供需撮合'],
    ['前端 A', 'apps/tourist', '游客端 22 个页面'],
    ['前端 B', 'apps/console', '管理端 12 个页面'],
  ];
  teams.forEach(([role, mod, desc], i) => {
    const y = 1.75 + i * 0.92;
    s.addText(role, { x: M + 0.1, y, w: 1.35, h: 0.7, fontFace: FONT, fontSize: 15, bold: true, color: PRIMARY, valign: 'middle', margin: 0 });
    s.addText(mod, { x: 1.85, y, w: 3.5, h: 0.7, fontFace: FONT, fontSize: 12.5, color: TEXT, valign: 'middle', margin: 0 });
    s.addText(desc, { x: 5.4, y, w: 3.4, h: 0.7, fontFace: FONT, fontSize: 12, color: MUTED, valign: 'middle', margin: 0 });
    if (i < teams.length - 1) s.addShape(pres.shapes.LINE, { x: M, y: y + 0.86, w: W - 2 * M, h: 0, line: { color: HAIRLINE, width: 1 } });
  });
  s.addText(
    [
      { text: '流程：', options: { bold: true, color: TEXT } },
      { text: 'feature 分支 → PR → CI 全绿 → 评审合并；公共层（core / api / db / packages）改动必须单独 PR 评审', options: { color: MUTED } },
    ],
    { x: 9.0, y: 1.85, w: 3.9, h: 1.9, fontFace: FONT, fontSize: 12, lineSpacingMultiple: 1.4, margin: 0, valign: 'top' },
  );
  stat(s, 9.15, 3.6, 1.8, 1.5, '30', '已合并 PR');
  stat(s, 11.15, 3.6, 1.8, 1.5, '2', '队友贡献 PR\n（迁移兼容修复）');
  s.addText('环境与协议一致：AGENTS.md 版本表 + check-env.sh 自检 + 锁文件（uv.lock / pnpm-lock）+ OpenAPI 契约先行', { x: M, y: 6.35, w: W - 2 * M, h: 0.5, fontFace: FONT, fontSize: 12.5, color: MUTED, margin: 0 });
}

// ============================== 12 进度与下一步 ==============================
{
  const s = pres.addSlide();
  head(s, '当前进度与下一步', '需求 2.x / 4.x 主线全部落地；剩余为外部输入与运维增强');
  s.addText('已完成', { x: M + 0.1, y: 1.7, w: 6, h: 0.4, fontFace: FONT, fontSize: 16, bold: true, color: PRIMARY, margin: 0 });
  s.addText(
    [
      { text: '需求 2.1–2.4 全部功能（行程 / 地图 / 装备 / 商城 / 供需）', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '需求 4.1 / 4.2 / 4.3 / 4.4：双角色审核、设备绑定自动登录、承载三档实测与在线客服', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '商城全闭环：下单 → 收货与地址簿 → 发货签收 → 售后单流转', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '12 个后端模块 + 双前端 + Nginx 网关 + 容器化部署（compose full）', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '质量与可观测：236 单测 / 93.7% 覆盖率 / 81 前端 / 17 项 e2e / 指标与请求追踪 / 三档压测', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '两轮并发审计修复 + 承载加固（池超时归零、依赖不可达 3 秒 503、502 根因修复）', options: { bullet: { code: '2022', indent: 12 } } },
    ],
    { x: M + 0.1, y: 2.15, w: 6.15, h: 4.6, fontFace: FONT, fontSize: 13, color: TEXT, paraSpaceAfter: 13, margin: 0, valign: 'top' },
  );
  s.addText('下一步', { x: 7.0, y: 1.7, w: 5.8, h: 0.4, fontFace: FONT, fontSize: 16, bold: true, color: ACCENT, margin: 0 });
  s.addText(
    [
      { text: '真实大模型接入：只改 .env（自部署千问 2.5 7B），接入后重测 AI 容量', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '真实支付：先落适配层（N13），取得资质后只实现 provider', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '备份与恢复演练（N16）· CI/CD 自动部署', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: 'RAG 向量检索升级（可选，先定向量载体）', options: { bullet: { code: '2022', indent: 12 }, breakLine: true } },
      { text: '演示环境一键化：容器化已就绪（make full-up）', options: { bullet: { code: '2022', indent: 12 } } },
    ],
    { x: 7.0, y: 2.15, w: 5.8, h: 4.6, fontFace: FONT, fontSize: 13, color: TEXT, paraSpaceAfter: 13, margin: 0, valign: 'top' },
  );
}

// ============================== 13 结尾 ==============================
{
  const s = pres.addSlide();
  s.background = { color: DARK };
  s.addText('谢谢聆听', { x: M, y: 2.4, w: W - 2 * M, h: 0.9, fontFace: FONT, fontSize: 40, bold: true, color: 'FFFFFF', align: 'center', margin: 0 });
  s.addText('欢迎现场体验完整演示链路', { x: M, y: 3.35, w: W - 2 * M, h: 0.5, fontFace: FONT, fontSize: 17, color: 'A8CBD4', align: 'center', margin: 0 });
  s.addShape(pres.shapes.LINE, { x: 5.6, y: 4.05, w: 2.1, h: 0, line: { color: ACCENT, width: 2 } });
  s.addText(
    [
      { text: '游客端  http://localhost:5173     管理端  http://localhost:5174', options: { breakLine: true } },
      { text: '演示账号：游客 13900001111 / 商户 13800000088 / 管理员 13800000000', options: {} },
    ],
    { x: M, y: 4.35, w: W - 2 * M, h: 0.9, fontFace: FONT, fontSize: 13.5, color: '8FB3BD', align: 'center', lineSpacingMultiple: 1.4, margin: 0 },
  );
}

pres.writeFile({ fileName: OUT }).then(() => console.log('已生成:', OUT));
