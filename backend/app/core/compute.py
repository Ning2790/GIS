"""计算核心的统一封装（业务模块只能经过这里）。

优先使用 C++ 扩展 qh_core（`make build-core` 构建，产物输出到 backend/）；
未编译时自动回退到等价的 Python 实现——CI 与未装编译器的机器也能跑通。
两套实现的公式必须保持一致（见 cpp_core/src/recommend.cpp 与 src/planning.cpp）。

注意：扩展是二进制产物，可能与源码不同步（例如别人拉下新代码但还没重新编译）。
新增函数按「函数级探测」回退：旧版 qh_core 缺哪个函数，哪个函数走 Python 实现，
不会因为扩展陈旧而报 AttributeError。
"""

import math

try:  # C++ 扩展为可选：缺失时回退到下面的 Python 实现
    import qh_core  # type: ignore[import-not-found]

    USING_CPP_CORE = True
except ImportError:
    qh_core = None  # type: ignore[assignment]
    USING_CPP_CORE = False


def _has_cpp(name: str) -> bool:
    return USING_CPP_CORE and hasattr(qh_core, name)


_EARTH_RADIUS_KM = 6371.0088
_DECAY_KM = 50.0  # 距离打分的半程衰减公里数


def _py_haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """与 cpp_core 同公式的 Python 回退实现（Haversine）。"""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    # 对跖点附近 a 会因浮点舍入略大于 1：不 clamp 则 math.asin 抛 ValueError
    # （C++ std::asin 则静默得 NaN），clamp 保证两实现行为一致。
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def _py_distance_score(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return 100.0 / (1.0 + _py_haversine_km(lat1, lng1, lat2, lng2) / _DECAY_KM)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间球面距离（公里）。"""
    if USING_CPP_CORE:
        return float(qh_core.haversine_km(lat1, lng1, lat2, lng2))
    return _py_haversine_km(lat1, lng1, lat2, lng2)


def distance_score(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """基于距离的推荐打分（0-100，越近越高）。"""
    if USING_CPP_CORE:
        return float(qh_core.distance_score(lat1, lng1, lat2, lng2))
    return _py_distance_score(lat1, lng1, lat2, lng2)


def _py_planning_score(name: str, city: str, keyword: str) -> float:
    """与 cpp_core/src/planning.cpp 同公式的 Python 回退实现（偏好相关性打分）。"""
    if not keyword:
        return 0.0
    if name:
        if name == keyword:
            return 100.0
        if keyword in name:
            coverage = len(keyword) / len(name)
            return 70.0 + 20.0 * coverage
        if name in keyword:
            return 65.0
    if city and keyword in city:
        return 60.0
    return 0.0


def _py_path_length_km(points: list[tuple[float, float]]) -> float:
    """与 cpp_core/src/route.cpp 同公式的 Python 回退实现（相邻点大圆距离累加）。"""
    total = 0.0
    for index in range(1, len(points)):
        lat1, lng1 = points[index - 1]
        lat2, lng2 = points[index]
        total += _py_haversine_km(lat1, lng1, lat2, lng2)
    return total


def path_length_km(points: list[tuple[float, float]]) -> float:
    """路径总里程（公里）：按顺序对相邻点做 Haversine 累加；少于两个点返回 0。"""
    if _has_cpp("path_length_km"):
        return float(qh_core.path_length_km(points))
    return _py_path_length_km(points)


def planning_score(name: str, city: str, keyword: str) -> float:
    """行程选点的偏好相关性打分（0-100）。

    偏好为空 → 0；名称完全相同 → 100；名称包含偏好 → 70 + 覆盖度 × 20；
    偏好（整句）提到景点名 → 65；城市包含偏好 → 60；否则 0。
    """
    if _has_cpp("planning_score"):
        return float(qh_core.planning_score(name, city, keyword))
    return _py_planning_score(name, city, keyword)


def planning_scores(names: list[str], cities: list[str], keyword: str) -> list[float]:
    """planning_score 的批量版本（names / cities 一一对应）。"""
    if len(names) != len(cities):
        raise ValueError("planning_scores: names 与 cities 长度必须一致")
    if _has_cpp("planning_scores"):
        return [float(score) for score in qh_core.planning_scores(names, cities, keyword)]
    pairs = zip(names, cities, strict=True)
    return [_py_planning_score(name, city, keyword) for name, city in pairs]
