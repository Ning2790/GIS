/** 响应类型（后端返回体）。
 *
 * 说明：后端路由统一返回 {code, msg, data} 信封、未声明 response_model，
 * OpenAPI 契约目前只覆盖**请求体**（生成于 schema.d.ts）；
 * 响应类型在此手写维护，字段以后端各模块的 schemas.py 为准，改动需同步。
 */

/** 后端统一响应信封。 */
export interface ApiEnvelope<T> {
  code: number;
  msg: string;
  data: T;
}

/** 分页响应的 data 形状（与 app/core/pagination.py 的 page_data 一致）。 */
export interface PageData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export type UserRole = 'tourist' | 'merchant' | 'enterprise' | 'admin';
export type UserStatus = 'active' | 'pending_review' | 'rejected' | 'disabled';

export interface UserPublic {
  id: number;
  phone: string;
  role: UserRole;
  status: UserStatus;
  nickname: string | null;
  license_no: string | null;
  license_file?: string | null;
  created_at: string;
}

/** 登录成功返回的令牌对与用户信息（auth/schemas.py TokenResponse）。 */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  refresh_token: string;
  refresh_expires_in: number;
  user: UserPublic;
}

/** 已登录设备（auth/schemas.py DevicePublic；需求 4.2 的设备绑定）。 */
export interface DevicePublic {
  id: number;
  device_label: string | null;
  last_ip: string | null;
  last_user_agent: string | null;
  first_seen_at: string;
  last_seen_at: string;
  /** 是否为当前请求所在设备（按 X-Device-Id 匹配）。 */
  is_current: boolean;
}

/** 景点（旅行列表项，travel/schemas.py AttractionPublic）。 */
export interface AttractionPublic {
  id: number;
  name: string;
  city: string;
  description: string;
  latitude: number | null;
  longitude: number | null;
  cover_image: string | null;
  distance_km: number | null;
}

/** 门票。 */
export interface TicketPublic {
  id: number;
  name: string;
  price: number;
  description: string | null;
}

/** 景点详情（含票种）。 */
export interface AttractionDetail extends AttractionPublic {
  tickets: TicketPublic[];
}

/** 地图底图图层（map/schemas.py MapLayerPublic）。 */
export interface MapLayerPublic {
  key: string;
  name: string;
  url_template: string;
  attribution: string;
}

/** 底图配置（三图）。 */
export interface MapConfig {
  layers: MapLayerPublic[];
  default: string;
}

/** 地图点位（坐标齐全的景点，map/schemas.py MapPointPublic）。 */
export interface MapPointPublic {
  id: number;
  name: string;
  city: string;
  latitude: number;
  longitude: number;
}

/** 点位查询响应。 */
export interface MapPointsData {
  points: MapPointPublic[];
  total: number;
}

/** 环境快照（gear/schemas.py WeatherSnapshotPublic）。 */
export interface WeatherSnapshotPublic {
  id: number;
  city: string;
  snapshot_date: string;
  temperature_c: number;
  soil_moisture_pct: number;
  altitude_m: number;
  pressure_hpa: number;
  source: string;
}

/** 装备建议（gear/schemas.py GearAdvicePublic）。 */
export interface GearAdvice {
  city: string;
  date: string;
  snapshot: WeatherSnapshotPublic;
  items: string[];
  notes: string | null;
}

/** B2B 供需信息（b2b/schemas.py B2bSupplyPublic / B2bDemandPublic 同构）。 */
export interface B2bPostPublic {
  id: number;
  user_id: number;
  title: string;
  category: string;
  region: string;
  quantity: number;
  unit: string;
  price_expect: number | null;
  description: string;
  status: string;
}

/** 知识库命中来源（ai/schemas.py KnowledgeSourceOut；N12 向量检索）。 */
export interface KnowledgeSource {
  topic: string;
  /** 余弦相似度（matched_by=keyword 时为命中词数）。 */
  score: number;
  /** vector = 语义命中 / keyword = 关键词回退。 */
  matched_by: string;
  excerpt: string;
}

/** 控制台首页概览（dashboard/schemas.py DashboardSummary）。 */
export interface DashboardSummary {
  role: string;
  my_products: number | null;
  my_products_on_sale: number | null;
  my_products_off_shelf: number | null;
  my_orders_created: number | null;
  my_orders_paid: number | null;
  my_orders_cancelled: number | null;
  today_orders: number | null;
  today_revenue: number | null;
  low_stock: number | null;
  low_stock_threshold: number | null;
  users_total: number | null;
  pending_reviews: number | null;
  products_total: number | null;
  cs_queue: number | null;
  recent_logs: AuditLogPublic[];
}

/** 平台文件（files/schemas.py FilePublic）。 */
export interface FilePublic {
  id: number;
  filename: string;
  content_type: string;
  size: number;
  /** 上传原始字节数（图片被压缩时与 size 对比可见压缩效果；非图片为 null）。 */
  original_size?: number | null;
  is_public: boolean;
  url: string;
  /** 缩略图地址（列表页用；无缩略图时为 null，前端回退 url）。 */
  thumbnail_url?: string | null;
}

/** 商品（shop/schemas.py ProductPublic）。 */
export interface ProductPublic {
  id: number;
  merchant_id: number;
  name: string;
  description: string;
  price: number;
  stock: number;
  status: string;
  image_url: string | null;
  /** 主图缩略图（列表页用；服务端无缩略图时自动回退原图）。 */
  image_thumbnail_url?: string | null;
  /** 全站收藏数（商户商品列表展示关注度；商品详情公开可见）。 */
  favorite_count?: number;
  created_at: string;
}

/** 销量看板（/shop/merchant/sales-overview）：近 N 天日趋势 + 热销 Top 5。 */
export interface SalesOverview {
  days: number;
  series: { date: string; orders: number; revenue: number }[];
  top_products: { name: string; quantity: number; revenue: number }[];
}

/** 搜索热词（/shop/hot-keywords）：关键词 + 窗口内的搜索次数。 */
export interface HotKeyword {
  keyword: string;
  count: number;
}

/** 站内通知（notifications/schemas.py NotificationPublic）。
 *
 * 触发点：支付成功 → 商户；发货 → 买家；售后申请 → 商户；售后结单 → 买家。
 * ref_type / ref_id 指向关联对象（order / after_sale），供前端跳转详情。
 */
export interface NotificationPublic {
  id: number;
  type: string;
  title: string;
  content: string;
  ref_type: string | null;
  ref_id: number | null;
  is_read: boolean;
  created_at: string;
}

/** 商品详情（shop/schemas.py ProductDetailPublic）：额外带收藏态。 */
export interface ProductDetail extends ProductPublic {
  /** 当前登录用户是否已收藏（未登录恒为 false）。 */
  is_favorited: boolean;
  favorite_count: number;
}

/** 首页推荐（/shop/recommendations）：basis 供前端定标题。 */
export interface RecommendationPage {
  items: ProductPublic[];
  /** personal = 为你推荐（按兴趣打分）；popular = 大家都在看（游客 / 新用户兜底）。 */
  basis: 'personal' | 'popular';
}

/** 购物车条目。 */
export interface CartItemPublic {
  id: number;
  product_id: number;
  name: string;
  price: number;
  quantity: number;
  amount: number;
  stock: number;
  available: boolean;
}

/** 购物车。 */
export interface Cart {
  items: CartItemPublic[];
  total_amount: number;
}

/** 订单项（下单时的商品快照）。 */
export interface OrderItemPublic {
  id: number;
  product_id: number;
  product_name: string;
  unit_price: number;
  quantity: number;
  amount: number;
}

/** 订单（列表项）。 */
export interface OrderPublic {
  id: number;
  user_id: number;
  merchant_id: number;
  amount: number;
  status: string;
  /** 支付截止时间（超时未支付会自动取消；历史订单可能为空）。 */
  expire_at: string | null;
  /** 取消原因：buyer（买家主动）/ expired（超时未支付）。 */
  cancel_reason: string | null;
  /** 收货信息快照（历史订单可能为空）。 */
  receiver_name: string | null;
  receiver_phone: string | null;
  receiver_address: string | null;
  /** 履约（N3）：发货 / 签收 / 完成。 */
  shipped_at: string | null;
  carrier: string | null;
  tracking_no: string | null;
  delivered_at: string | null;
  completed_at: string | null;
  created_at: string;
  paid_at: string | null;
  /** 最新支付单退款状态：none / pending（待退款）/ refunded。 */
  payment_refund_status?: string | null;
  /** 最新支付单 id（控制台列表登记退款用）。 */
  payment_id?: number | null;
}

/** 收货信息（下单必填；落库为订单快照）。 */
export interface ReceiverPayload {
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
}

/** 收货地址（users/schemas.py AddressPublic；个人中心维护）。 */
export interface AddressPublic {
  id: number;
  receiver_name: string;
  receiver_phone: string;
  address: string;
  is_default: boolean;
  created_at: string;
}

/** 新增 / 更新收货地址的请求体。 */
export interface AddressPayload {
  receiver_name: string;
  receiver_phone: string;
  address: string;
  is_default?: boolean;
}

/** 订单详情（含明细与最新支付单状态）。 */
export interface OrderDetail extends OrderPublic {
  items: OrderItemPublic[];
  payment_status: string | null;
  /** 最新支付单 id（供管理员模拟回调）。 */
  payment_id: number | null;
  /** 最近一条售后（需求 2.3 售后）：有值则展示售后进度入口。 */
  after_sale_id: number | null;
  after_sale_status: string | null;
}

/** 售后单（shop/schemas.py AfterSalePublic）。 */
export interface AfterSalePublic {
  id: number;
  order_id: number;
  user_id: number;
  merchant_id: number;
  reason: string;
  description: string | null;
  /** pending / processing / resolved / rejected / withdrawn */
  status: string;
  handler_id: number | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

/** 售后留言（买卖双方 / 管理员）。 */
export interface AfterSaleMessagePublic {
  id: number;
  author_id: number;
  /** buyer / merchant / admin */
  author_role: string;
  content: string;
  created_at: string;
}

/** 售后详情：单据 + 留言流 + 订单摘要。 */
export interface AfterSaleDetail extends AfterSalePublic {
  messages: AfterSaleMessagePublic[];
  order_amount: number | null;
  order_status: string | null;
}

/** 支付单（占位：平台不做资金池）。 */
export interface PaymentPublic {
  id: number;
  order_id: number;
  amount: number;
  channel: string;
  status: string;
  trade_no: string | null;
  created_at: string;
  paid_at: string | null;
  /** 退款状态：none / pending / refunded。 */
  refund_status?: string;
  refund_note?: string | null;
  refunded_at?: string | null;
}

/** AI 会话（ai/schemas.py AiConversationPublic）。 */
export interface AiConversationPublic {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

/** AI 会话消息。 */
export interface AiMessagePublic {
  id: number;
  role: string;
  content: string;
  knowledge_sources: KnowledgeSource[];
  created_at: string;
}

/** AI 会话详情（含消息）。 */
export interface AiConversationDetail extends AiConversationPublic {
  messages: AiMessagePublic[];
}

/** 行程（travel/schemas.py ItineraryPublic）。 */
export interface ItineraryPublic {
  id: number;
  user_id: number;
  title: string;
  days: number;
  budget: number | null;
  preferences: string;
  fitness: string | null;
  risk_notes: string | null;
  created_at: string;
  updated_at: string;
}

/** 行程停靠点（含景点名）。 */
export interface ItineraryStopPublic {
  id: number;
  attraction_id: number;
  attraction_name: string | null;
  day: number;
  position: number;
  note: string | null;
}

/** 行程详情（含停靠点）。 */
export interface ItineraryDetail extends ItineraryPublic {
  stops: ItineraryStopPublic[];
  /** 全程里程（公里）：停靠点都有坐标时给出（计算核心累加），否则为 null */
  total_distance_km: number | null;
}

/** 预设路线（travel/schemas.py RoutePublic）。 */
export interface RoutePublic {
  id: number;
  name: string;
  theme: string;
  days: number;
  budget: number | null;
  description: string;
  cover_image: string | null;
  stop_count: number;
  created_at: string;
}

/** 预设路线停靠点（含景点名与坐标）。 */
export interface RouteStopPublic {
  id: number;
  attraction_id: number;
  attraction_name: string | null;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  day: number;
  position: number;
  note: string | null;
}

/** 预设路线详情（含停靠点）。 */
export interface RouteDetail extends RoutePublic {
  stops: RouteStopPublic[];
  /** 全程里程（公里）：停靠点都有坐标时给出（计算核心累加），否则为 null */
  total_distance_km: number | null;
}

/** 客服会话（cs/schemas.py CsSessionPublic）。 */
export interface CsSessionPublic {
  id: number;
  user_id: number;
  status: string;
  agent_id: number | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

/** 客服消息。 */
export interface CsMessagePublic {
  id: number;
  session_id: number;
  sender_type: string;
  sender_id: number | null;
  content: string;
  created_at: string;
}

/** 发送消息结果（AI 接待时 reply 为自动应答）。 */
export interface CsSendResult {
  message: CsMessagePublic;
  reply: CsMessagePublic | null;
}

/** 管理视图用户（含资质文件地址，仅管理员接口返回，users/schemas.py UserAdminPublic）。 */
export interface UserAdminPublic extends UserPublic {
  license_file: string | null;
}

/** 审计日志条目（admin/schemas.py AuditLogPublic）。 */
export interface AuditLogPublic {
  id: number;
  /** 操作人用户 id；系统动作（如超时取消、自动确认收货）为 null。 */
  actor_id: number | null;
  action: string;
  target_type: string;
  target_id: number;
  detail: string | null;
  created_at: string;
}

/** 匹配项（b2b 规则匹配结果）。 */
export interface B2bMatchItem {
  score: number;
  supply: B2bPostPublic;
}

/** 匹配结果。 */
export interface B2bMatchResult {
  demand: B2bPostPublic;
  matches: B2bMatchItem[];
}

/** 运行指标汇总（dashboard/schemas；仅管理员，与 /metrics 同源）。 */
export interface MetricsSummary {
  requests_total: number;
  server_error_total: number;
  /** 全部路由聚合的 P95 延迟（秒）；无请求时为 null。 */
  latency_p95_seconds: number | null;
  latency_avg_seconds: number | null;
  rate_limit_hits_total: number;
  queue_rejections_total: number;
  stock_gate_drift_total: number;
  db_unavailable_total: number;
  db_unretryable_failure_total: number;
  /** 当前各类别在途请求数（view / trade / ai）。 */
  /** 各类别在途请求数（view / trade / auth / ai） */
  queue_inflight: Record<string, number>;
  queue_capacity: Record<string, number>;
}
