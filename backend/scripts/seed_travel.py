"""写入青海景点演示数据（幂等，可重复执行）。

用法（在 backend 目录下）：
    uv run python scripts/seed_travel.py

按景点名称去重：已存在的景点**更新描述 / 城市 / 坐标**（演示文案以本脚本为准），
票种仅在新建时写入。

数据来源与口径（2026-10-16 扩充）：
- 景点取自**公开的青海省 A 级旅游景区名录**（省文旅厅 / 统计局公开口径：5A 四家、各州 4A）
  **与各州代表性打卡点**（昆仑山口、阿尼玛卿雪山等非 A 级点位按公开常识口径收录），
  覆盖全部 8 个州市，便于地图与线路演示；
- 描述按公开常识撰写（玩法 / 提示），**票价为示意区间**（旺季参考公开报价，
  非实时报价、非官方数据），答辩口径见 docs/需求对照表.md 的「演示数据」说明；
- 23 个景点的详细介绍单独维护在 `scripts/travel_descriptions.py`，运行时覆盖下方列表里的短文案；
- 坐标为景点大致位置（演示用，非测绘精度）；
- 未收录已因生态保护停止接待的景区（如年保玉则）。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
# 同时把脚本目录加入路径：无论是直接运行本脚本，还是被 e2e 的 prepare_db 导入，
# 都能找到同目录的 travel_descriptions.py。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import func, select  # noqa: E402
from travel_descriptions import DETAILED_DESCRIPTIONS  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.modules.travel import repository  # noqa: E402
from app.modules.travel.models import Attraction, Ticket  # noqa: E402

SEED_ATTRACTIONS: list[dict] = [
    {
        "name": "青海湖",
        "city": "海南州",
        "description": (
            "青海湖古称「西海」，是中国最大的内陆咸水湖，湖面海拔约 3200 米，"
            "环湖一圈约 360 公里。湖水随季节与光线变换青蓝层次，"
            "7—8 月油菜花与湖岸相映，是环湖骑行的黄金季节。\n\n"
            "经典玩法：二郎剑景区看开阔湖面，黑马河守日出，环湖西路自驾看草原与湖泊交替。"
            "湖区风大日晒强，建议备防风外套与高倍防晒。"
        ),
        "latitude": 36.897,
        "longitude": 100.188,
        "tickets": [
            {"name": "旺季门票", "price": 100, "description": "4 月—10 月"},
            {"name": "淡季门票", "price": 50, "description": "11 月—次年 3 月"},
        ],
    },
    {
        "name": "茶卡盐湖",
        "city": "海西州",
        "description": (
            "茶卡盐湖被称为「天空之镜」：湖面浅而平澈，天光云影倒映如镜，"
            "是拍倒影大片的经典机位。景区内有小火车往返湖心，"
            "建议清晨或傍晚前往，光线柔和、人少出片。\n\n"
            "拍摄提示：穿亮色衣物更出片；湖面反光强烈，墨镜与防晒必备；"
            "下湖建议租用防水鞋套，注意盐壳湿滑。"
        ),
        "latitude": 36.699,
        "longitude": 99.086,
        "tickets": [
            {"name": "门票", "price": 60},
            {"name": "小火车往返", "price": 100, "description": "可选"},
        ],
    },
    {
        "name": "塔尔寺",
        "city": "西宁市",
        "description": (
            "塔尔寺始建于明洪武年间，是藏传佛教格鲁派创始人宗喀巴大师的诞生地，"
            "与甘丹、哲蚌等并称格鲁派六大寺院。寺内酥油花、壁画、堆绣"
            "被誉为「艺术三绝」，大金瓦殿与大经堂气势恢宏。\n\n"
            "参观提示：殿内多禁拍照，请遵循现场标识；转经筒与佛殿请按顺时针方向参观；"
            "高原台阶较多，请慢行缓行。"
        ),
        "latitude": 36.489,
        "longitude": 101.569,
        "tickets": [{"name": "门票", "price": 70}],
    },
    {
        "name": "门源百里油菜花海",
        "city": "海北州",
        "description": (
            "每年 7 月，祁连山下的门源盆地绵延百里的油菜花同时盛放，"
            "金色花海背倚雪山，是青海夏季最壮观的花海景观。"
            "观花台与照壁山是俯瞰全景的经典位置。\n\n"
            "花季提示：盛花期约在 7 月上中旬，早晚光线最佳；花海区域风大，注意防风保暖；"
            "旺季车流集中，建议错峰出行。"
        ),
        "latitude": 37.388,
        "longitude": 101.616,
        "tickets": [{"name": "门票", "price": 60, "description": "花季"}],
    },
    {
        "name": "大柴旦翡翠湖",
        "city": "海西州",
        "description": (
            "翡翠湖位于柴达木盆地北缘的大柴旦镇附近，是原盐湖矿区积水形成的盐湖群。"
            "湖水富含矿物质，在阳光下呈现翡翠绿、宝石蓝等层次色彩，"
            "与白色盐埂交织，宛如散落在戈壁上的翡翠。\n\n"
            "游览提示：湖区无遮阳，防晒与饮水要充足；各湖池颜色随光线变化，"
            "午间色彩最艳；周边为自驾线路，注意戈壁路段行车安全。"
        ),
        "latitude": 37.848,
        "longitude": 95.257,
        "tickets": [{"name": "门票", "price": 120}],
    },
    {
        "name": "祁连卓尔山",
        "city": "海北州",
        "description": (
            "卓尔山被称为「东方小瑞士」：赤红丹霞与青绿草原层叠交错，"
            "对面即是终年积雪的牛心山，八月油菜花与青稞田把山谷染成棋盘。"
            "观景台可俯瞰祁连县城与八宝河谷全景。\n\n"
            "游览提示：山顶风大、紫外线强；日出与日落光线最柔，"
            "建议与门源花海串成一条北线行程。"
        ),
        "latitude": 38.183,
        "longitude": 100.243,
        "tickets": [
            {"name": "门票", "price": 60},
            {"name": "区间车（往返）", "price": 20, "description": "可选"},
        ],
    },
    {
        "name": "阿咪东索景区",
        "city": "海北州",
        "description": (
            "阿咪东索（藏语「千兵哨卡」）是祁连山的标志性雪峰之一，海拔约 4600 米，"
            "山下黑河峡谷与原始云杉林相间，是国家 5A 级旅游景区。"
            "景区以雪山、林海与高原牧场的组合见长，夏季凉爽宜人。\n\n"
            "游览提示：海拔较高，抵达当日避免剧烈活动；山区天气多变，"
            "备好防风防雨外层；自驾注意山路弯多坡陡。"
        ),
        "latitude": 38.152,
        "longitude": 100.318,
        "tickets": [
            {"name": "门票", "price": 60},
            {"name": "观光车", "price": 24, "description": "可选（与门票套票合计约 84 元）"},
        ],
    },
    {
        "name": "金银滩·原子城",
        "city": "海北州",
        "description": (
            "金银滩草原是中国第一颗原子弹与氢弹的研制基地旧址所在地；"
            "原子城纪念馆用实物与影像讲述「两弹一星」历程，"
            "草原一侧则是王洛宾写下《在那遥远的地方》的地方。\n\n"
            "参观提示：纪念馆多为免费预约参观、周一闭馆（以现场公告为准）；"
            "草原海拔约 3200 米，夏季凉爽，注意防晒与保暖。"
        ),
        "latitude": 36.917,
        "longitude": 100.994,
        "tickets": [
            {"name": "纪念馆", "price": 0, "description": "免费预约（以现场公告为准）"},
            {"name": "草原景区", "price": 30, "description": "示意价格"},
        ],
    },
    {
        "name": "互助土族故土园",
        "city": "海东市",
        "description": (
            "互助是全国唯一的土族自治县，故土园以土族民俗为核心："
            "安昭舞、轮子秋、土族盘绣与青稞酒酿造技艺在此集中展示，"
            "园内还有土族风情村落与民俗演艺。是国家 5A 级旅游景区。\n\n"
            "游览提示：可参与民俗互动与青稞酒品鉴（驾车者勿饮酒）；"
            "距西宁约 40 分钟车程，适合半日游。"
        ),
        "latitude": 36.843,
        "longitude": 101.955,
        "tickets": [
            {"name": "门票", "price": 90},
            {"name": "民俗演艺", "price": 40, "description": "可选"},
        ],
    },
    {
        "name": "互助北山国家森林公园",
        "city": "海东市",
        "description": (
            "北山森林公园地处祁连山南麓，以原始森林、峡谷与瀑布群著称，"
            "浪士当峡与扎龙沟是主要游线，夏季平均气温约 15℃，"
            "是西宁周边的避暑首选。\n\n"
            "游览提示：林区多雨，备防滑鞋与雨具；沟内徒步距离较长，量力而行；"
            "秋季白桦林转黄，是赏秋好去处。"
        ),
        "latitude": 36.962,
        "longitude": 102.402,
        "tickets": [{"name": "门票", "price": 50}],
    },
    {
        "name": "孟达天池",
        "city": "海东市",
        "description": (
            "孟达天池位于循化撒拉族自治县，是黄土高原与青藏高原过渡带上的"
            "森林湖泊，被誉为「青藏高原西双版纳」，湖畔云杉挺拔、湖水碧绿，"
            "是国家级自然保护区内的知名景观。\n\n"
            "游览提示：保护区生态脆弱，请勿采摘与丢弃垃圾；"
            "海拔约 2500 米，从停车场到天池需徒步上行，请穿舒适鞋。"
        ),
        "latitude": 35.852,
        "longitude": 102.601,
        "tickets": [{"name": "门票", "price": 65}],
    },
    {
        "name": "贵德国家地质公园",
        "city": "海南州",
        "description": (
            "「天下黄河贵德清」——贵德的黄河水清澈见底，与丹霞地貌相映成趣。"
            "阿什贡七彩峰丛以赭红、土黄、灰白的层理山体著称，"
            "是地质科普与出片的双料目的地。\n\n"
            "游览提示：丹霞观赏区日照强、无遮蔽，备好防晒与饮水；"
            "可与黄河清湿地公园、玉皇阁串线，一整天刚好。"
        ),
        "latitude": 36.043,
        "longitude": 101.404,
        "tickets": [{"name": "门票", "price": 80, "description": "含电瓶车与讲解（示意）"}],
    },
    {
        "name": "龙羊峡景区",
        "city": "海南州",
        "description": (
            "黄河上游第一座大型梯级电站形成的高峡平湖，峡谷陡峭、湖水深邃，"
            "被称作「中国的科罗拉多」。龙羊峡水库是黄河干流最大的人工湖之一，"
            "大坝与土林地貌是主要看点。\n\n"
            "游览提示：大坝观景与峡谷游船受水位与天气影响，出行前确认开放情况；"
            "顺路可去共和县看青海湖东岸。"
        ),
        "latitude": 36.129,
        "longitude": 100.918,
        "tickets": [
            {"name": "门票（龙羊湖）", "price": 50},
            {"name": "大峡谷 + 大坝联票", "price": 75, "description": "含观景台"},
            {"name": "游船", "price": 50, "description": "可选"},
        ],
    },
    {
        "name": "水上雅丹",
        "city": "海西州",
        "description": (
            "乌素特（水上）雅丹是柴达木盆地的奇观：干旱雅丹地貌被湖水包围，"
            "土丘如舰队浮在碧蓝水面上，日落时呈现金红与靛蓝的强对比，"
            "是近年爆火的摄影目的地。\n\n"
            "游览提示：地处戈壁，昼夜温差极大、补给点稀少，"
            "务必满油出发并带足饮水；手机信号断续，注意行车安全；"
            "夏季蚊虫较多，备驱蚊用品。"
        ),
        "latitude": 37.619,
        "longitude": 93.751,
        "tickets": [
            {"name": "门票", "price": 60, "description": "示意价格"},
            {"name": "区间车（往返）", "price": 60},
        ],
    },
    {
        "name": "察尔汗盐湖",
        "city": "海西州",
        "description": (
            "察尔汗盐湖是中国最大的盐湖，盐储量可供全世界食用上千年，"
            "「万丈盐桥」路基由盐壳筑成，湖面盐花与盐晶在阳光下晶莹耀眼。\n\n"
            "游览提示：与格尔木市区约 60 公里，多为盐碱戈壁路段；"
            "湖水与盐壳反光强烈，墨镜与防晒必备；参观请遵循景区指定区域。"
        ),
        "latitude": 36.802,
        "longitude": 95.306,
        "tickets": [{"name": "门票", "price": 100}],
    },
    {
        "name": "昆仑山口",
        "city": "海西州",
        "description": (
            "昆仑山口海拔约 4767 米，是青藏公路（G109）穿越昆仑山的垭口，"
            "立有昆仑山口碑与索南达杰纪念碑，是自驾进藏路上的重要地标"
            "（可可西里保护区核心区禁止进入，在垭口远观即可）。\n\n"
            "游览提示：此处海拔高、含氧量低，停留时间宜短，避免奔跑与剧烈活动；"
            "有基础疾病或感冒未愈者不建议前往；垭口风大寒冷，注意保暖。"
        ),
        "latitude": 35.652,
        "longitude": 94.069,
        "tickets": [],  # 公路垭口不收门票（不造虚构票种）
    },
    {
        "name": "坎布拉国家森林公园",
        "city": "黄南州",
        "description": (
            "坎布拉以丹霞赤壁、森林与黄河库区（李家峡）同框著称，"
            "「赤壁丹崖夹碧水」是它的标志画面；藏语意为「康巴人的庄园」。\n\n"
            "游览提示：观景平台与游船受季节影响，出行前确认；"
            "山路弯多，建议乘景区交通或包车前往；秋季层林斑斓最适合摄影。"
        ),
        "latitude": 36.114,
        "longitude": 101.849,
        "tickets": [
            {"name": "门票", "price": 100},
            {"name": "游船", "price": 150, "description": "可选"},
        ],
    },
    {
        "name": "热贡·隆务寺",
        "city": "黄南州",
        "description": (
            "同仁（藏语「热贡」）是国家级历史文化名城，「热贡艺术」"
            "（唐卡、泥塑、堆绣）在此代代相传，隆务寺是当地格鲁派大寺，"
            "周边吾屯村几乎家家有画师。\n\n"
            "参观提示：寺内与画院请遵循指引、拍摄前征得同意；"
            "农历正月与六月有传统法会，是体验热贡文化的窗口。"
        ),
        "latitude": 35.517,
        "longitude": 102.017,
        "tickets": [{"name": "门票", "price": 60}],
    },
    {
        "name": "青海藏文化博物院",
        "city": "西宁市",
        "description": (
            "馆藏以藏医药与藏族文化艺术见长，镇馆之宝是长 618 米的"
            "《中国藏族文化艺术彩绘大观》长卷，另设藏医史与藏药标本展厅，"
            "是了解高原民族医药与艺术的高效一站。\n\n"
            "参观提示：室内场馆，雨天备选；长卷展厅光线较暗，"
            "预留 2 小时以上参观时间更从容。"
        ),
        "latitude": 36.660,
        "longitude": 101.752,
        "tickets": [{"name": "门票", "price": 60}],
    },
    {
        "name": "丹噶尔古城",
        "city": "西宁市",
        "description": (
            "湟源丹噶尔是唐蕃古道与茶马古道上的商贸重镇，"
            "明清老街保存完好，城隍庙、文庙、商号与排灯文化构成"
            "「高原小北京」的市井底色。\n\n"
            "游览提示：古城与日月山、青海湖顺路，适合作为环湖线路的第一站；"
            "街区内有湟源陈醋、酿皮等地方小吃。"
        ),
        "latitude": 36.686,
        "longitude": 101.263,
        "tickets": [{"name": "门票", "price": 50, "description": "示意价格"}],
    },
    {
        "name": "日月山",
        "city": "西宁市",
        "description": (
            "日月山是黄土高原与青藏高原的地理分界，也是农业区与牧业区、"
            "汉文化与藏文化的交界，文成公主入藏的故事在此流传，"
            "山口的日亭与月亭是标志景观。\n\n"
            "游览提示：海拔约 3500 米、山口风大，注意保暖与防高反；"
            "与倒淌河、青海湖连成经典首日线路。"
        ),
        "latitude": 36.440,
        "longitude": 101.083,
        "tickets": [{"name": "门票", "price": 30, "description": "示意价格"}],
    },
    {
        "name": "新寨嘉那玛尼石经城",
        "city": "玉树州",
        "description": (
            "嘉那玛尼石经城由二十多亿块玛尼石堆叠而成，是吉尼斯认证的"
            "「世界最大玛尼堆」，转经道环绕石经城一周，藏地信众与游客同行。\n\n"
            "游览提示：请按顺时针方向转经，不攀爬石堆、不移动玛尼石；"
            "玉树海拔约 3700 米，抵达当日注意休息、避免饮酒与剧烈运动。"
        ),
        "latitude": 33.021,
        "longitude": 97.029,
        "tickets": [{"name": "门票", "price": 0, "description": "免费（示意）"}],
    },
    {
        "name": "阿尼玛卿雪山",
        "city": "果洛州",
        "description": (
            "阿尼玛卿是昆仑山系东段的主峰群，海拔 6282 米，"
            "藏语意为「爷爷大山」，是藏区著名的神山之一，"
            "雪山、冰川与高山草甸构成壮观的高原景观带。\n\n"
            "游览提示：属高原深处区域，路况与海拔都具挑战性，"
            "建议随有经验的车队或向导前往，做好高反预案与物资储备；"
            "尊重当地信仰与生态，不进入未开放区域。"
        ),
        "latitude": 34.512,
        "longitude": 99.407,
        "tickets": [{"name": "门票", "price": 0, "description": "自然景观，不收门票（示意）"}],
    },
]

# 详细文案以此为准：覆盖列表里的演示短文案（seed_travel 仍保留短版便于速览）。
for _item in SEED_ATTRACTIONS:
    if _item["name"] in DETAILED_DESCRIPTIONS:
        _item["description"] = DETAILED_DESCRIPTIONS[_item["name"]]


def main() -> None:
    created = 0
    updated = 0
    tickets_added = 0
    tickets_updated = 0
    tickets_removed = 0
    with SessionLocal() as db:
        for item in SEED_ATTRACTIONS:
            attraction = db.scalar(select(Attraction).where(Attraction.name == item["name"]))
            if attraction is not None:
                # 演示文案同步：重跑脚本即更新描述 / 城市 / 坐标
                attraction.city = item["city"]
                attraction.description = item["description"]
                attraction.latitude = item["latitude"]
                attraction.longitude = item["longitude"]
                # 票种**以脚本为准**：按名称 upsert（更新价格 / 说明、补齐缺失），
                # 并删除脚本清单之外的票种——否则改价、改名、删票种重跑都不生效
                # （复审实测：改票价重跑后库里仍是旧价；改名/删票种会留下残行）。
                # 注意：脚本管理的演示景点上手工加的票种会被清掉（演示数据以本脚本为准）。
                current_tickets = {
                    ticket.name: ticket
                    for ticket in db.scalars(
                        select(Ticket).where(Ticket.attraction_id == attraction.id)
                    )
                }
                for name, ticket in current_tickets.items():
                    if name not in {item["name"] for item in item["tickets"]}:
                        db.delete(ticket)
                        tickets_removed += 1
                for ticket in item["tickets"]:
                    current = current_tickets.get(ticket["name"])
                    if current is None:
                        db.add(
                            Ticket(
                                attraction_id=attraction.id,
                                name=ticket["name"],
                                price=ticket["price"],
                                description=ticket.get("description"),
                            )
                        )
                        tickets_added += 1
                    else:
                        current.price = ticket["price"]
                        current.description = ticket.get("description")
                        tickets_updated += 1
                updated += 1
                continue
            attraction = Attraction(
                name=item["name"],
                city=item["city"],
                description=item["description"],
                latitude=item["latitude"],
                longitude=item["longitude"],
            )
            db.add(attraction)
            db.flush()
            for ticket in item["tickets"]:
                db.add(
                    Ticket(
                        attraction_id=attraction.id,
                        name=ticket["name"],
                        price=ticket["price"],
                        description=ticket.get("description"),
                    )
                )
            created += 1
        db.commit()
        total = db.scalar(select(func.count()).select_from(Attraction)) or 0
        geo_updated = repository.backfill_geom(db)
        db.commit()  # backfill_geom 只 flush，提交由调用方负责

    print(
        f"已写入 {created} 个新景点、更新 {updated} 个景点文案"
        f"（票种新增 {tickets_added}、更新 {tickets_updated}、移除 {tickets_removed}）；"
        f"当前共 {total} 个景点。"
    )
    if geo_updated:
        print(f"已回填 {geo_updated} 个景点的 PostGIS 坐标（geom）。")


if __name__ == "__main__":
    main()
