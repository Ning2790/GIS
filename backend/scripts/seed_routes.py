"""写入青海经典预设路线（幂等，可重复执行）。

用法（在 backend 目录下）：
    uv run python scripts/seed_routes.py

依赖景点数据：先跑 `uv run python scripts/seed_travel.py`。
按路线名称去重：已存在的路线**更新主题 / 天数 / 预算 / 描述并整体重建停靠点**
（演示文案以本脚本为准）。停靠点按景点名称关联，缺失的景点会被跳过并提示。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import delete, func, select  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.travel.models import Attraction, Route, RouteStop  # noqa: E402

SEED_ROUTES: list[dict] = [
    {
        "name": "青海湖 + 茶卡经典 3 日环线",
        "theme": "环湖",
        "days": 3,
        "budget": 1280,
        "description": (
            "第一次来青海的「必修课」：从西宁出发，先到塔尔寺感受藏传佛教艺术，"
            "再一路向西奔赴青海湖与茶卡盐湖。节奏前紧后松，"
            "把最开阔的湖景留在第二天清晨的日出。\n\n"
            "适合人群：首次入青、时间有限但想看到「湖 + 盐湖 + 人文」三大元素的游客。"
            "高原首日避免剧烈运动，环湖路段风大，注意防风与防晒。"
        ),
        "stops": [
            {"attraction": "塔尔寺", "day": 1, "note": "上午抵达，重点看大金瓦殿与酥油花馆"},
            {"attraction": "青海湖", "day": 1, "note": "下午二郎剑景区看开阔湖面"},
            {"attraction": "青海湖", "day": 2, "note": "黑马河段守日出，随后沿环湖西路自驾"},
            {"attraction": "茶卡盐湖", "day": 2, "note": "傍晚光线柔和，拍倒影最佳"},
            {"attraction": "茶卡盐湖", "day": 3, "note": "上午补拍或乘小火车，午后返程"},
        ],
    },
    {
        "name": "柴达木秘境摄影 4 日线",
        "theme": "摄影",
        "days": 4,
        "budget": 2180,
        "description": (
            "为出片而生的西线深度线路：以茶卡盐湖的「天空之镜」为序，"
            "深入柴达木盆地看大柴旦翡翠湖的碧色盐池，再折返青海湖收尾。"
            "戈壁路段车程较长，把摄影时间留给清晨与黄昏。\n\n"
            "适合人群：摄影爱好者、二次入青的游客。建议携带偏振镜与备用电池，"
            "戈壁昼夜温差大，注意保暖与补水。"
        ),
        "stops": [
            {"attraction": "茶卡盐湖", "day": 1, "note": "下午入园，等日落前后的镜面效果"},
            {"attraction": "大柴旦翡翠湖", "day": 2, "note": "午间色彩最艳，各盐池颜色随光线变化"},
            {"attraction": "大柴旦翡翠湖", "day": 3, "note": "清晨再入湖区补拍，午后返程东行"},
            {"attraction": "青海湖", "day": 4, "note": "环湖东路收尾，湖岸线条适合大场景"},
        ],
    },
    {
        "name": "花海人文 2 日短线",
        "theme": "人文",
        "days": 2,
        "budget": 760,
        "description": (
            "把青海人文与自然的两张名片串成一条短线：第一天在塔尔寺看「艺术三绝」，"
            "第二天北上祁连山下，看门源百里油菜花海如何铺满整个盆地。\n\n"
            "适合人群：周末出行、家庭游客；花季（7 月上中旬）体验最佳，"
            "淡季可将门源替换为沿途草原风光，行程同样成立。"
        ),
        "stops": [
            {"attraction": "塔尔寺", "day": 1, "note": "殿内请勿拍照，顺时针参观"},
            {"attraction": "门源百里油菜花海", "day": 2, "note": "观花台俯瞰全景，早晚光线最佳"},
        ],
    },
    {
        "name": "青海大环线 5 日精华",
        "theme": "环湖",
        "days": 5,
        "budget": 2880,
        "description": (
            "把青海东西两线的精华一次走完：西宁出发经门源花海北上，"
            "再一路向西穿越祁连山与柴达木盆地，从翡翠湖、茶卡盐湖到青海湖，"
            "最后回到西宁。适合把它当作「一次看全青海」的路线。\n\n"
            "适合人群：假期充裕的自驾 / 包车游客。全程车程较长，"
            "建议每天出发前确认油量与天气，高原反应明显时及时下撤休息。"
        ),
        "stops": [
            {"attraction": "门源百里油菜花海", "day": 1, "note": "清晨从西宁出发，下午观花台"},
            {"attraction": "塔尔寺", "day": 1, "note": "返程顺路补人文一站（视到达时间）"},
            {"attraction": "大柴旦翡翠湖", "day": 2, "note": "穿祁连山抵达，午后入湖区"},
            {"attraction": "大柴旦翡翠湖", "day": 3, "note": "清晨补拍后向东返程"},
            {"attraction": "茶卡盐湖", "day": 3, "note": "傍晚踩点天空之镜"},
            {"attraction": "青海湖", "day": 4, "note": "黑马河住宿，次日守日出"},
            {"attraction": "青海湖", "day": 5, "note": "环湖骑行或自驾一段后返回西宁"},
        ],
    },
    {
        "name": "祁连山花海 3 日北线",
        "theme": "赏花",
        "days": 3,
        "budget": 1480,
        "description": (
            "七月的祁连山北麓是一场金色与绿色的大合唱：门源百里花海、"
            "祁连卓尔山的丹霞草原、阿咪东索的雪峰林海依次展开，"
            "节奏舒缓、海拔友好，适合家庭出行。\n\n"
            "适合人群：暑期赏花、亲子出游。花季为 7 月上中旬，"
            "旺季住宿务必提前预订；草原昼夜温差大，记得带保暖外层。"
        ),
        "stops": [
            {"attraction": "门源百里油菜花海", "day": 1, "note": "下午抵达观花台，日落金光"},
            {"attraction": "祁连卓尔山", "day": 2, "note": "上午上山俯瞰八宝河谷"},
            {"attraction": "阿咪东索景区", "day": 2, "note": "下午看雪峰与云杉林"},
            {"attraction": "祁连卓尔山", "day": 3, "note": "清晨补拍后经达坂山返回西宁"},
        ],
    },
    {
        "name": "黄河风情 2 日线（贵德 + 坎布拉）",
        "theme": "人文",
        "days": 2,
        "budget": 980,
        "description": (
            "「天下黄河贵德清」——这条线把清澈的黄河水、阿什贡丹霞与"
            "坎布拉的赤壁碧水串在一起，是青海人文与地质景观的浓缩。\n\n"
            "适合人群：短线出行、省会周边游。丹霞区域日照强烈，"
            "防晒与饮水要备足；坎布拉山路弯多，建议包车或乘景区交通。"
        ),
        "stops": [
            {"attraction": "贵德国家地质公园", "day": 1, "note": "上午阿什贡看七彩峰丛"},
            {"attraction": "龙羊峡景区", "day": 1, "note": "下午看高峡平湖"},
            {"attraction": "坎布拉国家森林公园", "day": 2, "note": "全天：观景台 + 黄河库区游船"},
        ],
    },
    {
        "name": "柴达木深度摄影 5 日线",
        "theme": "摄影",
        "days": 5,
        "budget": 2680,
        "description": (
            "为镜头而走的西线大环：水上雅丹的落日、翡翠湖的碧色盐池、"
            "察尔汗的万丈盐桥与昆仑山口的雪线，"
            "一路是戈壁与盐湖构成的极简画面。\n\n"
            "适合人群：摄影爱好者 / 自驾老手。路段补给稀疏、"
            "手机信号断续，请满油出发、结伴同行，并预留天气机动天。"
        ),
        "stops": [
            {"attraction": "茶卡盐湖", "day": 1, "note": "首日黄昏踩点天空之镜"},
            {"attraction": "水上雅丹", "day": 2, "note": "午后抵达，守日落蓝调"},
            {"attraction": "大柴旦翡翠湖", "day": 3, "note": "清晨光线最净，午间色彩最艳"},
            {"attraction": "察尔汗盐湖", "day": 4, "note": "万丈盐桥 + 盐花特写"},
            {"attraction": "昆仑山口", "day": 4, "note": "昆仑山口碑打卡（停留宜短）"},
            {"attraction": "青海湖", "day": 5, "note": "回程绕湖一段收尾"},
        ],
    },
    {
        "name": "非遗人文 2 日线（塔尔寺 + 热贡 + 互助）",
        "theme": "人文",
        "days": 2,
        "budget": 1080,
        "description": (
            "把青海的非遗与民俗看点串成一条线：塔尔寺的「艺术三绝」、"
            "同仁热贡的唐卡画院、互助土族的盘绣与安昭舞，"
            "适合想深入了解高原文化的游客。\n\n"
            "参观提示：寺院与画院请遵循现场指引，拍摄前先征得同意；"
            "尊重当地信仰与习俗，不触摸文物与唐卡。"
        ),
        "stops": [
            {"attraction": "塔尔寺", "day": 1, "note": "上午：大金瓦殿、酥油花馆"},
            {"attraction": "热贡·隆务寺", "day": 1, "note": "下午：隆务寺与吾屯画院"},
            {"attraction": "坎布拉国家森林公园", "day": 2, "note": "上午顺路看丹霞与库区"},
            {"attraction": "互助土族故土园", "day": 2, "note": "下午民俗体验 + 品鉴青稞酒"},
        ],
    },
    {
        "name": "玉树康巴文化 4 日线",
        "theme": "人文",
        "days": 4,
        "budget": 2380,
        "description": (
            "深入三江源方向，看嘉那玛尼石经城的世界最大玛尼堆与玉树的康巴风情，"
            "一条海拔较高、文化浓度极高的线路。\n\n"
            "高原提示：玉树海拔约 3700 米，建议提前适应并备好药物，"
            "抵达当日不饮酒、不剧烈运动；冬季路况与气温要求更高，"
            "请关注实时交通与天气信息。"
        ),
        "stops": [
            {"attraction": "青海湖", "day": 1, "note": "首日以低海拔适应为主"},
            {"attraction": "阿尼玛卿雪山", "day": 2, "note": "远观雪山群，随车队行进"},
            {"attraction": "新寨嘉那玛尼石经城", "day": 3, "note": "顺时针转经一周"},
            {"attraction": "新寨嘉那玛尼石经城", "day": 4, "note": "清晨补拍后返程"},
        ],
    },
    {
        "name": "省会周边 1 日人文线（日月山 + 丹噶尔 + 博物院）",
        "theme": "人文",
        "days": 1,
        "budget": 480,
        "description": (
            "时间有限也能看懂青海：从日月山的地理分界，到丹噶尔古城的"
            "茶马市井，再到藏文化博物院的 618 米长卷，"
            "一天把「地理、商道、艺术」三条线走一遍。\n\n"
            "适合人群：西宁中转、会议间隙或高原适应日。"
            "高原第一天建议以低强度行程为主，避免剧烈活动。"
        ),
        "stops": [
            {"attraction": "日月山", "day": 1, "note": "上午：日亭月亭与分界碑"},
            {"attraction": "丹噶尔古城", "day": 1, "note": "中午：老街与湟源小吃"},
            {"attraction": "青海藏文化博物院", "day": 1, "note": "下午：长卷与藏医药展厅"},
        ],
    },
]


def main() -> None:
    created = 0
    updated = 0
    missing: set[str] = set()
    with SessionLocal() as db:
        attractions = {
            name: attraction_id
            for attraction_id, name in db.execute(select(Attraction.id, Attraction.name)).all()
        }
        for item in SEED_ROUTES:
            route = db.scalar(select(Route).where(Route.name == item["name"]))
            if route is None:
                route = Route(
                    name=item["name"],
                    theme=item["theme"],
                    days=item["days"],
                    budget=item["budget"],
                    description=item["description"],
                )
                db.add(route)
                db.flush()
                created += 1
            else:
                # 演示文案同步：重跑脚本即更新主题 / 天数 / 预算 / 描述
                route.theme = item["theme"]
                route.days = item["days"]
                route.budget = item["budget"]
                route.description = item["description"]
                updated += 1

            # 停靠点整体重建：先删后插，避免历史残留
            db.execute(delete(RouteStop).where(RouteStop.route_id == route.id))
            day_counters: dict[int, int] = {}
            for stop in item["stops"]:
                attraction_id = attractions.get(stop["attraction"])
                if attraction_id is None:
                    missing.add(stop["attraction"])
                    continue
                day_counters[stop["day"]] = day_counters.get(stop["day"], 0) + 1
                db.add(
                    RouteStop(
                        route_id=route.id,
                        attraction_id=attraction_id,
                        day=stop["day"],
                        position=day_counters[stop["day"]],
                        note=stop["note"],
                    )
                )
        db.commit()
        total = db.scalar(select(func.count()).select_from(Route)) or 0
        stop_total = db.scalar(select(func.count()).select_from(RouteStop)) or 0

    print(f"已写入 {created} 条新路线、更新 {updated} 条路线；")
    print(f"当前共 {total} 条路线、{stop_total} 个停靠点。")
    if missing:
        print(f"⚠ 以下景点不存在，相关停靠点已跳过：{'、'.join(sorted(missing))}")


if __name__ == "__main__":
    main()
