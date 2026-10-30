"""应用配置。

所有可变项集中在此，通过环境变量或 .env 覆盖（环境变量优先级高于 .env）。
"""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 开发默认密钥：仅允许在 ENV=dev 下使用；非开发环境必须通过 JWT_SECRET 覆盖。
DEFAULT_JWT_SECRET = "dev-only-secret-change-me-in-production-32b+"


class Settings(BaseSettings):
    """全局配置。环境变量名与字段名一致，不区分大小写。"""

    # 运行环境：dev（默认）/ prod 等。非 dev 时会强制校验关键密钥不是默认值。
    env: str = "dev"

    app_name: str = "青海旅游 + 农产品平台"
    api_v1_prefix: str = "/api/v1"

    # 默认 SQLite：未安装 Docker 的机器也能把闭环跑通。
    # 接入 docker-compose 的 PostgreSQL 时改为（用 127.0.0.1，Docker 只发布 IPv4）：
    #   postgresql+psycopg://qh:dev@127.0.0.1:5432/qh_platform
    database_url: str = "sqlite:///./dev.db"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    # 访问令牌短时效，配合 /api/v1/auth/refresh 的刷新令牌使用（见 auth 模块）。
    access_token_expire_minutes: int = 30
    # 刷新令牌重放检测的宽限窗口（秒）：轮换后此窗口内的二次使用视为并发刷新竞态，
    # 仅拒绝；超出则判定为重放并撤销整个轮换家族（见 auth.service.refresh）。
    refresh_reuse_grace_seconds: int = 10
    # 「记住我」未勾选时的刷新令牌有效期（小时）：短期会话，适合公共电脑；
    # 勾选时为 30 天（auth.service.REFRESH_TOKEN_EXPIRE_DAYS）。
    refresh_token_short_expire_hours: int = 12

    # 部署在受信反向代理（Nginx，见 deploy/）之后时设为 true：
    # 接口限流按 X-Forwarded-For 识别来源 IP（代理须覆写该头）。
    # 服务端口直接对外暴露时不要开启（客户端可伪造 XFF 绕过 IP 限流）。
    trust_proxy_headers: bool = False

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
    ]

    # 大模型（统一入口见 app/core/llm.py）。默认 mock：无需密钥即可跑通全链路；
    # 接云端（兼容 OpenAI 协议）只改这几项并设 AI_PROVIDER=openai。
    ai_provider: str = "mock"
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = "qwen2.5"
    ai_timeout_seconds: int = 30

    # Redis 连接串（交易预扣闸门 / 限流、排队共用）。
    # 留空表示不启用：相关功能自动降级（例如库存扣减直接走数据库条件更新）。
    redis_url: str = ""

    # 接口限流（P1 承载能力，见 app/core/rate_limit.py）：固定窗口计数，按分钟。
    # 阈值 <= 0 或 Redis 不可用时放行（fail-open）；生产可在 .env 收紧。
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 20  # 登录（按 IP，防撞库）
    rate_limit_register_per_minute: int = 10  # 注册（按 IP，防批量注册）
    rate_limit_order_per_minute: int = 60  # 下单 / 结算（按用户，防刷单）
    rate_limit_ai_per_minute: int = 15  # AI 问答（按用户，防刷模型）

    # 单机排队闸门（P1 承载能力，见 app/core/queue_gate.py）：按类别限制"在途请求数"，
    # 超限返回 503「排队中」；交易类独立配额——查看类超载不影响交易（优先保障交易）。
    # 0 或 QUEUE_ENABLED=false 表示不限；数值以压测（S6）为准，先给保守默认。
    queue_enabled: bool = True
    # 容量与连接池对齐的原则：**闸门要先拦，别让请求排到池超时**（实测：池 20+20=40
    # 连接时，交易在途 >60 就会出现等连接超时）。数值来自 2026-10-15 的双实例实测
    # （见 docs/压测报告.md「闸门与连接池容量对齐」）：
    queue_max_view: int = 200  # 普通查看类（毫秒级读，实测不压垮池）
    # 交易类（下单 / 结算 / 支付）：取实测**在途**安全值（41 安全 / 67 起等连接超时）的保守值
    queue_max_trade: int = 50
    # 认证类：只含 bcrypt 端点（登录 / 注册 / 改密）；refresh 等轻量端点不在此档
    queue_max_auth: int = 20
    queue_max_ai: int = 30  # AI 类（模型调用慢，容量最小；接真实模型后需重测）

    # 热点读缓存（P1 承载能力，见 app/core/cache.py）：景点 / 商品列表等高频读。
    # Redis 不可用时自动降级为直查数据库；写路径通过版本号（bump）立即失效。
    cache_enabled: bool = True
    cache_ttl_seconds: int = 60

    # 待支付订单超时自动取消（N1）：下单后超过该分钟数未支付，定时任务自动取消并回补库存。
    # 演示时可临时调小（如 1）以便实测。
    order_expire_minutes: int = 30

    # 订单履约自动确认收货（N3）：签收后该天数内买家未确认收货则自动确认；
    # 若商户一直未标记签收，则发货后 _fallback 天兜底自动确认（订单不会永远悬着）。
    order_auto_confirm_days: int = 7
    order_auto_confirm_fallback_days: int = 15

    # 售后有效期（N4）：订单「已完成」后该天数内可申请售后；已支付 / 已发货阶段不限时。
    after_sale_window_days: int = 15

    # 数据保留期（维护卡 P0+P1）：只增不减的行为 / 日志类数据按保留期清理，0 = 关闭该类清理。
    # 默认值即推荐值（口径见 docs/数据增长与归档方案.md）；批大小与单表单次上限用于限速，
    # 避免大表一次删太多造成长事务与锁等待。
    retention_ai_messages_days: int = 365
    retention_cs_messages_days: int = 365
    retention_product_views_days: int = 180
    retention_audit_logs_days: int = 365
    retention_weather_snapshots_days: int = 30
    retention_inventory_days: int = 365
    retention_notifications_days: int = 365
    retention_batch_size: int = 1000  # 每批删除条数
    retention_max_per_run: int = 50000  # 单表单次运行删除上限（超出留到下次）

    # MinIO 对象存储（P2 资质文件上传，见 files 模块）。
    # 留空 endpoint 表示上传接口不可用（503）；docker-compose 默认凭据如下。
    minio_endpoint: str = ""  # 如 127.0.0.1:9000
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "qh-files"
    minio_secure: bool = False  # 本地容器不启用 TLS；接对象存储网关时设 true
    file_max_mb: int = 10  # 单文件大小上限（MB）
    file_allowed_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]
    # 图片处理（需求 4.1）：上传时压缩 + 生成缩略图，列表页用缩略图、详情页用原图。
    # max_edge=0 关闭原图压缩；thumbnail_edge=0 关闭缩略图（两者都只影响新上传的文件，
    # 存量文件可用 backend/scripts/make_thumbnails.py 补缩略图）。
    image_max_edge: int = 1600  # 原图长边上限（像素，等比缩放，不放大）
    image_jpeg_quality: int = 82  # JPEG / WebP 重编码质量（1-100）
    image_thumbnail_edge: int = 400  # 缩略图长边（像素）

    # 数据库连接池（P1 承载能力）：与同步端点的默认线程池（40）匹配——
    # 池太小会让请求排队等连接，太大则给数据库压力；按机器与 PG max_connections 调整。
    db_pool_size: int = 20
    db_max_overflow: int = 20
    db_pool_timeout: int = 5  # 等连接超时（秒）：快速失败而不是挂死
    # 建立连接超时（秒，PostgreSQL）：库不可达时快速失败。刻意**小于** db_pool_timeout
    # ——要让「连不上」先暴露，否则请求会先耗尽连接池、被误记成过载（pool_timeout）。
    # 注意 libpq 会把 <2 的值钳到 2 秒，0/负值等于不超时（回到挂死）；见 docs/部署.md。
    db_connect_timeout: int = 3
    # 语句超时（毫秒，PostgreSQL；0 = 不设）：一条慢查询会长期占住连接与工作线程，
    # 应用侧兜底（connect_timeout 只约束"连不上"）。默认 10s——超过它的正常业务查询
    # 说明需要优化或异步化，而不是让连接被拖住；后台任务/迁移可单独调大或关掉。
    db_statement_timeout_ms: int = 10_000

    # 日志与请求追踪（N8）：慢请求阈值（毫秒；<= 0 关闭慢请求日志）
    slow_request_ms: int = 500

    # 向量检索（N12）：默认 mock 确定性嵌入（无外网/密钥，演示可复现）；
    # 接真实嵌入模型只改这里（OpenAI 兼容协议，如 vLLM 部署的嵌入模型）。
    embedding_provider: str = "mock"  # mock | openai
    embedding_dim: int = 1024  # mock 向量维度（真实模型按服务返回，不用改）
    # 维度/模型与库内向量不一致时，检索会跳过向量路径并告警（见 ai/knowledge.py）——
    # 换嵌入实现后必须重跑 scripts/seed_knowledge.py 重算向量
    embedding_model: str = ""  # 真实模型名（provider=openai 时必填）
    embedding_base_url: str = ""  # 如 http://127.0.0.1:8001/v1
    embedding_api_key: str = ""
    embedding_timeout_seconds: int = 10
    rag_top_k: int = 3  # 检索返回条数上限
    rag_min_score: float = 0.24  # 低于该余弦相似度不算向量命中（关键词路径仍独立生效）
    # 二级命中（非首位）的展示门槛：只影响「参考平台知识」卡片与落库来源，
    # 低于它仍会作为 prompt 上下文（弱命中进提示词有益、进卡片会误导）
    rag_secondary_min_score: float = 0.4

    # 支付网关（N13）：mock = 占位实现（复刻既有「管理员模拟回调」行为，无支付链接）。
    # 接支付宝 / 微信时实现 app/modules/shop/payment_gateway.py 的协议并在此切换。
    payment_gateway: str = "mock"

    # 气象数据源（gear 需求 2.2）：openmeteo = Open-Meteo 真实源（免密钥，见 weather_provider.py）；
    # mock = 确定性模拟源（离线演示 / 断网回退）。真实源逐城失败跳过，整批失败自动回退模拟源。
    weather_provider: str = "openmeteo"
    weather_timeout_seconds: int = 10
    # 真实源接口基址（默认官方地址；自建代理或测试打桩时覆盖）
    weather_base_url: str = "https://api.open-meteo.com/v1/forecast"

    # Celery broker（定时采集等后台任务）。留空 = 不启动 worker，手动脚本不受影响。
    celery_broker_url: str = ""

    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    @model_validator(mode="after")
    def _check_production_secrets(self) -> "Settings":
        """非开发环境不允许使用默认密钥启动（否则任何人可伪造令牌）。"""
        if self.env != "dev" and self.jwt_secret == DEFAULT_JWT_SECRET:
            raise ValueError(
                "非开发环境（ENV != dev）必须通过 JWT_SECRET 配置独立密钥，当前仍是默认值"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
