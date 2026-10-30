"""本地压测脚本（Locust，P1d 承载能力验收用）。

用法（在 backend 目录执行；locust 为一次性依赖，不进项目依赖）：
    # 1) 起服务（放宽限流，避免压测自身的注册/登录被限流挡住）
    RATE_LIMIT_REGISTER_PER_MINUTE=2000 RATE_LIMIT_LOGIN_PER_MINUTE=2000 \
        uv run uvicorn app.main:app --port 8765

    # 2) 压测（示例：50 并发、30 秒）
    uv run --with locust locust -f scripts/loadtest.py --headless \
        -u 50 -r 10 -t 30s --host http://127.0.0.1:8765

按需求 4.3 的三档容量分别验收（`LOADTEST_PROFILE` 选档，见 docs/压测报告.md）：
    # 读档：5000 人同时在线查看 ≈ 83–167 req/s
    LOADTEST_PROFILE=read  ... -u 500 -r 100 -t 60s --host http://127.0.0.1:9080
    # 交易档：500 人同时交易 ≈ 17–25 单/s
    LOADTEST_PROFILE=trade ... -u 200 -r 40  -t 60s --host http://127.0.0.1:9080
    # AI 档：100 人同时 AI 搜索 ≈ 5 次/s（mock 模型；接真实模型须另测）
    LOADTEST_PROFILE=ai    ... -u 100 -r 20  -t 75s --host http://127.0.0.1:9080

    9080 = 压测专用网关（deploy/nginx/nginx.loadtest.conf，双实例 least_conn、无单 IP 限流；
    轮询版对照见 deploy/nginx/nginx.loadtest-rr.conf）。
    对着生产网关（8443）压测会先被 rl_* 限流拦下——那本身就是一层验收，见报告「网关档」。

**分档为什么要靠 LOADTEST_PROFILE（而不是 `--tags`）**：Locust 的 `-u` 会按 weight 把并发
**分摊给模块里所有用户类**，`--tags` 只过滤「任务」——被过滤类的 on_start 仍会执行、并发名额
也被占走。若用 `--tags read` 跑 500 并发，真正在浏览的只有约 3/5 的用户类（权重 6/10），
测出来的是打折的容量；交叉验证过 `--tags` 还会让被过滤类报「No tasks defined」并让进程
以非 0 退出。故按档位在**导入期剔除**无关用户类，`-u` 才全量落在目标场景。
`@tag` 仅作标注（文档 / IDE 过滤用），不参与分档。

场景贴近需求 4.3（读多写少 + 交易链路 + AI）：
    - BrowseUser（权重 6，tag read）：景点列表（命中缓存）/ 商品列表 / 根路径
    - ShoppingUser（权重 2，tag trade）：注册 → 登录 → 幂等下单（用 test_start 准备的压测商品）
    - AiUser（权重 1）：AI 问答（mock 模型），混合场景用（节奏偏快）
    - AiSearchUser（权重 1，tag ai）：AI 档专用，真实节奏（每人约 20s 一次提问）

说明：
- 队列闸门 / 限流按服务真实配置生效——若调小容量，压测会如实出现 503 / 429（即被测行为）；
- test_start 会直连数据库准备"压测商户 + 大库存商品"（幂等，可重复执行）。
"""

import os
import uuid

from locust import HttpUser, between, events, tag, task

_PROFILES = {"mixed", "read", "trade", "ai"}
# 档位：mixed（默认，全场景混合）/ read / trade / ai
PROFILE = os.getenv("LOADTEST_PROFILE", "mixed").strip().lower()
if PROFILE not in _PROFILES:
    # 静默跑成混合档会让人误以为测的是目标场景，直接报错退出
    raise SystemExit(f"LOADTEST_PROFILE={PROFILE!r} 无效，可选：{sorted(_PROFILES)}")

LOADTEST_PHONE = "13800000099"
LOADTEST_PASSWORD = "Loadtest123456"
LOADTEST_PRODUCT_STOCK = 10**7

_state: dict = {"product_id": None}


@events.test_start.add_listener
def _prepare(environment, **_kwargs) -> None:  # noqa: ANN001
    """直连数据库准备压测商户与大库存商品（幂等）。"""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.modules.shop.models import Product, ProductStatus
    from app.modules.users.models import User, UserRole, UserStatus

    with SessionLocal() as db:
        merchant = db.scalar(select(User).where(User.phone == LOADTEST_PHONE))
        if merchant is None:
            merchant = User(
                phone=LOADTEST_PHONE,
                password_hash=hash_password(LOADTEST_PASSWORD),
                role=UserRole.MERCHANT,
                status=UserStatus.ACTIVE,
                nickname="压测商户",
            )
            db.add(merchant)
            db.commit()
            db.refresh(merchant)
        product = db.scalar(
            select(Product).where(Product.merchant_id == merchant.id, Product.name == "压测商品")
        )
        if product is None:
            product = Product(
                merchant_id=merchant.id,
                name="压测商品",
                description="loadtest",
                price=1,
                stock=LOADTEST_PRODUCT_STOCK,
                status=ProductStatus.ON_SALE,
            )
            db.add(product)
            db.commit()
            db.refresh(product)
        _state["product_id"] = product.id


@tag("read")
class BrowseUser(HttpUser):
    """浏览类（读多写少，缓存命中路径）。"""

    weight = 6
    wait_time = between(0.05, 0.2)

    @task(3)
    def attractions(self) -> None:
        self.client.get(
            "/api/v1/travel/attractions",
            params={"page": 1, "page_size": 10},
            name="/travel/attractions",
        )

    @task(2)
    def products(self) -> None:
        self.client.get(
            "/api/v1/shop/products",
            params={"page": 1, "page_size": 10},
            name="/shop/products",
        )

    @task(1)
    def root(self) -> None:
        self.client.get("/")


@tag("trade")
class ShoppingUser(HttpUser):
    """交易链路：注册 → 登录 → 幂等下单。"""

    weight = 2
    wait_time = between(0.5, 2)

    def on_start(self) -> None:
        self.phone = "139" + uuid.uuid4().hex[:8]
        self.headers: dict[str, str] = {}
        self.client.post(
            "/api/v1/auth/register/tourist",
            json={"phone": self.phone, "password": "Load123456"},
            name="/auth/register",
        )
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"phone": self.phone, "password": "Load123456"},
            name="/auth/login",
        )
        if resp.status_code == 200:
            self.headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    @task
    def order(self) -> None:
        if not self.headers or _state["product_id"] is None:
            return
        self.client.post(
            "/api/v1/shop/orders",
            json={
                "receiver_name": "压测收货人",
                "receiver_phone": "13800000000",
                "receiver_address": "青海省西宁市城西区压测路 1 号",
                "product_id": _state["product_id"],
                "quantity": 1,
                "idem_key": uuid.uuid4().hex,
            },
            headers=self.headers,
            name="/shop/orders",
        )


class AiUser(HttpUser):
    """AI 问答（mock 模型，验证慢接口路径）——混合场景用，节奏偏快。

    单跑 AI 档（100 人同时搜索）用下面的 AiSearchUser（真实节奏）。
    """

    weight = 1
    wait_time = between(2, 5)

    def on_start(self) -> None:
        self.phone = "137" + uuid.uuid4().hex[:8]
        self.headers: dict[str, str] = {}
        self.client.post(
            "/api/v1/auth/register/tourist",
            json={"phone": self.phone, "password": "Load123456"},
            name="/auth/register",
        )
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"phone": self.phone, "password": "Load123456"},
            name="/auth/login",
        )
        if resp.status_code == 200:
            self.headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    @task
    def ask(self) -> None:
        if not self.headers:
            return
        self.client.post(
            "/api/v1/ai/ask",
            json={"question": "青海湖什么时候去最好？"},
            headers=self.headers,
            name="/ai/ask",
        )


# ---- 档位生效（放在**所有用户类定义之后**，见文件末尾）----


@tag("ai")
class AiSearchUser(HttpUser):
    """AI 档（需求 4.3「100 人同时 AI 搜索」）：真实节奏——每人约 20s 问一次。

    100 并发 × 20s 一次 ≈ 5 req/s（换算见 docs/压测报告.md）。mock 模型；
    接真实模型后受模型服务并发与首字延迟限制，须**另测**并据此调 QUEUE_MAX_AI。
    """

    weight = 1
    wait_time = between(15, 25)

    def on_start(self) -> None:
        self.phone = "136" + uuid.uuid4().hex[:8]
        self.headers: dict[str, str] = {}
        self.client.post(
            "/api/v1/auth/register/tourist",
            json={"phone": self.phone, "password": "Load123456"},
            name="/auth/register",
        )
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"phone": self.phone, "password": "Load123456"},
            name="/auth/login",
        )
        if resp.status_code == 200:
            self.headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

    @task
    def ask(self) -> None:
        if not self.headers:
            return
        self.client.post(
            "/api/v1/ai/ask",
            json={"question": "青海湖什么时候去最好？"},
            headers=self.headers,
            name="/ai/ask",
        )


# ---- 档位生效（必须在所有用户类定义之后）----
# 把非目标用户类置 None：Locust 只收集「是 User 子类」的模块属性，None 会被忽略，
# `-u` 于是全量落在目标场景。用 `--tags` 做不到——它只过滤「任务」，被过滤类的
# on_start 仍会执行、并发名额照样占走（实测目标场景只拿到 1/5～1/10 的并发）。
_DROP_BY_PROFILE = {
    "read": ("ShoppingUser", "AiUser", "AiSearchUser"),
    "trade": ("BrowseUser", "AiUser", "AiSearchUser"),
    "ai": ("BrowseUser", "ShoppingUser", "AiUser"),
}
for _name in _DROP_BY_PROFILE.get(PROFILE, ()):
    globals()[_name] = None
