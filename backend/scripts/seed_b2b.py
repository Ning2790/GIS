"""写入 B2B 供需演示数据（幂等，可重复执行）。

用法（在 backend 目录下）：
    uv run python scripts/seed_b2b.py

- 演示商户：手机号 13800000088 / 密码 Demo123456（已存在则复用）；
- 按 (标题) 去重：同名已存在则跳过。价格为演示数据，仅供开发调试。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.b2b.models import B2bDemand, B2bStatus, B2bSupply  # noqa: E402
from app.modules.users.models import User, UserRole, UserStatus  # noqa: E402

DEMO_PHONE = "13800000088"
DEMO_PASSWORD = "Demo123456"

DEMO_SUPPLIES: list[dict] = [
    {
        "title": "祁连山牦牛肉干直供",
        "category": "肉制品",
        "region": "海北州",
        "quantity": 5,
        "unit": "吨",
        "price_expect": 180000,
        "description": "祁连山牧场散养牦牛，风干工艺，可按规格分装；支持长期稳定供货。",
    },
    {
        "title": "柴达木黑枸杞批发",
        "category": "枸杞",
        "region": "海西州",
        "quantity": 2,
        "unit": "吨",
        "price_expect": 80000,
        "description": "柴达木盆地野生黑枸杞，花青素含量高，礼盒与散装均可。",
    },
    {
        "title": "湟中青稞（新粮）",
        "category": "粮食",
        "region": "海东市",
        "quantity": 50,
        "unit": "吨",
        "price_expect": 2600,
        "description": "当年新收青稞，颗粒饱满、杂质少，适合酿酒与食品加工。",
    },
    {
        "title": "贵德菜籽油（小榨）",
        "category": "食用油",
        "region": "海南州",
        "quantity": 10,
        "unit": "吨",
        "price_expect": 14000,
        "description": "高原油菜籽小榨工艺，浓香型，可提供质检报告。",
    },
    # ---- 2026-10-16 扩充：按青海特色农产品补到 15 条供给（演示数据，价格示意）----
    {
        "title": "互助青稞酒原酒供应",
        "category": "酒类",
        "region": "海东市",
        "quantity": 20,
        "unit": "吨",
        "price_expect": 16000,
        "description": "互助青稞酒厂原酒，清香型与浓香型可选，支持贴牌与定制度数。",
    },
    {
        "title": "乐都紫皮大蒜产地直供",
        "category": "蔬菜",
        "region": "海东市",
        "quantity": 30,
        "unit": "吨",
        "price_expect": 6200,
        "description": "乐都紫皮蒜，瓣大辛辣耐储；可分级包装，支持长期供货。",
    },
    {
        "title": "互助马铃薯（淀粉加工用）",
        "category": "粮食",
        "region": "海东市",
        "quantity": 200,
        "unit": "吨",
        "price_expect": 1500,
        "description": "高原马铃薯，淀粉含量高，适合淀粉与粉条加工；起订量可谈。",
    },
    {
        "title": "柴达木湖盐原盐批发",
        "category": "调味品",
        "region": "海西州",
        "quantity": 50,
        "unit": "吨",
        "price_expect": 600,
        "description": "柴达木盐湖天然原盐（茶卡 / 察尔汗产区），颗粒均匀；"
        "可提供检测报告，支持散装与分装。",
    },
    {
        "title": "祁连黄蘑菇干货供应",
        "category": "食用菌",
        "region": "海北州",
        "quantity": 2,
        "unit": "吨",
        "price_expect": 240000,
        "description": "草原野生黄蘑菇晒干货，香气浓郁；分级筛选，适合礼盒与餐饮渠道。",
    },
    {
        "title": "门源油菜花蜜（蜂场直供）",
        "category": "蜂产品",
        "region": "海北州",
        "quantity": 15,
        "unit": "吨",
        "price_expect": 26000,
        "description": "花季成熟蜜，波美度达标；可贴牌分装，附蜂蜜检测报告。",
    },
    {
        "title": "湟源陈醋（手工老醋）",
        "category": "调味品",
        "region": "西宁市",
        "quantity": 20,
        "unit": "吨",
        "price_expect": 8500,
        "description": "传统工艺陈醋，酸香醇厚；桶装散醋与瓶装成品均可供应。",
    },
    {
        "title": "牦牛绒原料（分梳绒）",
        "category": "纺织原料",
        "region": "海北州",
        "quantity": 5,
        "unit": "吨",
        "price_expect": 320000,
        "description": "祁连牦牛绒分梳原料，纤维细度与长度指标可按批次提供检测数据。",
    },
    {
        "title": "枸杞芽茶（茶园直供）",
        "category": "茶叶",
        "region": "海西州",
        "quantity": 3,
        "unit": "吨",
        "price_expect": 120000,
        "description": "春季头茬枸杞芽制茶，清香微苦；可代加工包装，供货稳定。",
    },
    {
        "title": "野生沙棘果（冷冻果）",
        "category": "林果",
        "region": "海东市",
        "quantity": 40,
        "unit": "吨",
        "price_expect": 3800,
        "description": "高原野生沙棘果，酸度足、色素高；冷冻运输，适合原浆与饮料加工。",
    },
    {
        "title": "青稞藜麦杂粮礼盒代工",
        "category": "食品加工",
        "region": "西宁市",
        "quantity": 20000,
        "unit": "盒",
        "price_expect": 45,
        "description": "按品牌方需求代工杂粮礼盒（青稞 / 藜麦 / 燕麦组合），支持定制包装与条码。",
    },
]

DEMO_DEMANDS: list[dict] = [
    {
        "title": "长期收购牦牛肉干",
        "category": "肉制品",
        "region": "西宁市",
        "quantity": 10,
        "unit": "吨",
        "price_expect": 165000,
        "description": "食品加工厂常年收购高原牦牛肉干原料，要求有检疫与质检证明。",
    },
    {
        "title": "求购酿酒用青稞",
        "category": "粮食",
        "region": "西宁市",
        "quantity": 100,
        "unit": "吨",
        "price_expect": 2500,
        "description": "酒厂收购酿酒用青稞，水分与杂质指标按国标执行，可分批交货。",
    },
    {
        "title": "求购有机马铃薯",
        "category": "蔬菜",
        "region": "海东市",
        "quantity": 50,
        "unit": "吨",
        "price_expect": 1800,
        "description": "连锁商超供应商求购有机认证马铃薯，需提供产地证明。",
    },
    # ---- 2026-10-16 扩充：补到 10 条需求（演示数据，价格示意）----
    {
        "title": "连锁超市长期求购青海藜麦",
        "category": "粮食",
        "region": "西宁市",
        "quantity": 60,
        "unit": "吨",
        "price_expect": 9000,
        "description": "连锁商超自有品牌寻高原藜麦稳定货源，要求分级一致、可月度供货。",
    },
    {
        "title": "电商平台寻黑枸杞货源",
        "category": "枸杞",
        "region": "海西州",
        "quantity": 5,
        "unit": "吨",
        "price_expect": 76000,
        "description": "电商平台寻柴达木黑枸杞供应链，需支持一件代发与礼盒分装。",
    },
    {
        "title": "餐饮连锁求购速冻牦牛肉",
        "category": "肉制品",
        "region": "西宁市",
        "quantity": 30,
        "unit": "吨",
        "price_expect": 62000,
        "description": "火锅连锁求购速冻牦牛肉卷 / 块，需检疫与冷链资质，长期合作。",
    },
    {
        "title": "出口贸易商求购有机红枸杞",
        "category": "枸杞",
        "region": "海西州",
        "quantity": 20,
        "unit": "吨",
        "price_expect": 40000,
        "description": "出口标准红枸杞，需有机认证与农残检测报告，可分批交割。",
    },
    {
        "title": "药企求购藏红花（含质检）",
        "category": "中药材",
        "region": "西宁市",
        "quantity": 200,
        "unit": "公斤",
        "price_expect": 9000,
        "description": "制药企业采购藏红花原料，需提供含量检测与产地证明，长期合作优先。",
    },
    {
        "title": "奶茶连锁求购青稞粉与糌粑",
        "category": "食品加工",
        "region": "西宁市",
        "quantity": 80,
        "unit": "吨",
        "price_expect": 11000,
        "description": "茶饮连锁开发高原谷物系列，寻青稞粉 / 糌粑原料，需稳定批次与供货周期。",
    },
    {
        "title": "酒店与民宿求购地方食材年度供应",
        "category": "综合",
        "region": "海北州",
        "quantity": 1,
        "unit": "批",
        "price_expect": 380000,
        "description": "环湖酒店群年度采购：菜籽油、黄蘑菇、牦牛酸奶、青稞制品等本地食材打包供应。",
    },
]


def main() -> None:
    created_supply = 0
    created_demand = 0
    with SessionLocal() as db:
        merchant = db.scalar(select(User).where(User.phone == DEMO_PHONE))
        if merchant is None:
            merchant = User(
                phone=DEMO_PHONE,
                password_hash=hash_password(DEMO_PASSWORD),
                role=UserRole.MERCHANT,
                status=UserStatus.ACTIVE,
                nickname="演示商户",
            )
            db.add(merchant)
            db.flush()

        for item in DEMO_SUPPLIES:
            exists = db.scalar(select(B2bSupply).where(B2bSupply.title == item["title"]))
            if exists is not None:
                continue
            db.add(B2bSupply(user_id=merchant.id, status=B2bStatus.OPEN, **item))
            created_supply += 1

        for item in DEMO_DEMANDS:
            exists = db.scalar(select(B2bDemand).where(B2bDemand.title == item["title"]))
            if exists is not None:
                continue
            db.add(B2bDemand(user_id=merchant.id, status=B2bStatus.OPEN, **item))
            created_demand += 1

        db.commit()
        supply_total = db.scalar(select(func.count()).select_from(B2bSupply)) or 0
        demand_total = db.scalar(select(func.count()).select_from(B2bDemand)) or 0

    print(
        f"已写入 {created_supply} 条供给、{created_demand} 条需求（同名跳过）；"
        f"当前共 {supply_total} 条供给、{demand_total} 条需求。"
    )


if __name__ == "__main__":
    main()
