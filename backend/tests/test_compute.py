"""计算核心封装测试：Python 回退的正确性与 C++ 实现的一致性。"""

import math

import pytest

from app.core import compute

# 精确构造的近对跖坐标对：a（Haversine 中间量）越 1 达 2 ULP（1.0000000000000004），
# sqrt(a) > 1 使 math.asin 真实抛 ValueError（C++ std::asin 则得 NaN）。
# 它是 clamp 的强回归用例：去掉 min(1.0, a) 后本用例必然失败。
_ANTIPODAL_PAIR = (65.23655595123734, 155.21888059145596, -65.2365559507342, -24.78111940793167)


def test_haversine_known_distance() -> None:
    # 西宁（36.617, 101.778）→ 青海湖（36.897, 100.188）：约 145 公里
    distance = compute.haversine_km(36.617, 101.778, 36.897, 100.188)
    assert 120 < distance < 170


def test_haversine_zero_and_symmetry() -> None:
    assert compute.haversine_km(36.6, 101.7, 36.6, 101.7) == pytest.approx(0.0)
    forward = compute.haversine_km(36.6, 101.7, 36.9, 100.2)
    backward = compute.haversine_km(36.9, 100.2, 36.6, 101.7)
    assert forward == pytest.approx(backward)


def test_haversine_antipodal_no_domain_error() -> None:
    """对跖点（地球两端）与近对跖极端坐标：两种实现都必须安全返回半周长。"""
    half_circumference = math.pi * 6371.0088
    for coords in [(0.0, 0.0, 0.0, 180.0), _ANTIPODAL_PAIR]:
        assert compute.haversine_km(*coords) == pytest.approx(half_circumference, rel=1e-9)
        assert compute._py_haversine_km(*coords) == pytest.approx(half_circumference, rel=1e-9)


def test_distance_score_bounds_and_monotonic() -> None:
    near = compute.distance_score(36.6, 101.7, 36.61, 101.71)
    far = compute.distance_score(36.6, 101.7, 36.9, 100.2)
    assert 0 <= far < near <= 100


def test_cpp_matches_python_when_built() -> None:
    """C++ 扩展已构建时：两种实现应在数值上一致（当前本机 make build-core 的验收点）。"""
    if not compute.USING_CPP_CORE:
        pytest.skip("C++ 扩展未构建（走 Python 回退），本项跳过")
    for coords in [
        (36.6, 101.7, 36.9, 100.2),
        (0.0, 0.0, 0.0, 1.0),
        (36.617, 101.778, 36.897, 100.188),
        _ANTIPODAL_PAIR,
    ]:
        assert compute.haversine_km(*coords) == pytest.approx(
            compute._py_haversine_km(*coords), rel=1e-9
        )
        assert compute.distance_score(*coords) == pytest.approx(
            compute._py_distance_score(*coords), rel=1e-9
        )


def test_planning_score_preference_matching() -> None:
    """行程选点打分：偏好为空 / 全名 / 名称包含 / 整句提到 / 城市命中 / 不命中。"""
    assert compute.planning_score("青海湖", "海南州", "") == 0.0
    assert compute.planning_score("青海湖", "海南州", "青海湖") == 100.0
    # 名称包含偏好：覆盖度越高分越高（70 起，封顶 90）
    partial = compute.planning_score("青海湖", "海南州", "青海")
    assert 70.0 <= partial < 90.0
    assert partial < compute.planning_score("青海湖", "海南州", "青海湖")
    # 偏好是一整句话、其中提到景点全名
    assert compute.planning_score("青海湖", "海南州", "想看湖，想去青海湖") == 65.0
    # 城市命中
    assert compute.planning_score("茶卡盐湖", "海西州", "海西") == 60.0
    # 都不命中
    assert compute.planning_score("茶卡盐湖", "海西州", "完全无关") == 0.0
    # 三种命中的分数关系：全名 > 名称包含 > 整句提到 > 城市命中 > 不命中
    assert (
        compute.planning_score("青海湖", "海南州", "青海湖")
        > partial
        > compute.planning_score("青海湖", "海南州", "想看青海湖日出")
        > compute.planning_score("青海湖", "海南州", "海南州")
        > compute.planning_score("青海湖", "海南州", "无关")
    )


def test_planning_scores_batch_matches_single() -> None:
    """批量打分与逐个打分一致；长度不一致直接报错。"""
    names = ["青海湖", "茶卡盐湖", "塔尔寺"]
    cities = ["海南州", "海西州", "西宁市"]
    keyword = "青海"
    batch = compute.planning_scores(names, cities, keyword)
    pairs = list(zip(names, cities, strict=True))
    assert batch == [compute.planning_score(n, c, keyword) for n, c in pairs]
    assert batch == [compute._py_planning_score(n, c, keyword) for n, c in pairs]
    with pytest.raises(ValueError):
        compute.planning_scores(["青海湖"], [], "青海")


def test_planning_cpp_matches_python_when_built() -> None:
    """C++ 扩展已构建时：选点打分两套实现一致（含中文与空串边界）。"""
    if not compute._has_cpp("planning_scores"):
        pytest.skip("C++ 扩展未构建或版本过旧（回退 Python 实现），本项跳过")
    cases = [
        ("青海湖", "海南州", "青海湖"),
        ("青海湖", "海南州", "青海"),
        ("青海湖", "海南州", "想看青海湖日出"),
        ("茶卡盐湖", "海西州", "海西"),
        ("大柴旦翡翠湖", "海西州", "翡翠"),
        ("塔尔寺", "西宁市", ""),
        ("塔尔寺", "西宁市", "无关"),
        ("", "西宁市", "西宁"),
        ("ABC 景区", "测试市", "ABC"),
    ]
    for name, city, keyword in cases:
        assert compute.planning_score(name, city, keyword) == pytest.approx(
            compute._py_planning_score(name, city, keyword), rel=1e-12
        ), (name, city, keyword)


def test_path_length_km_basic_and_parity() -> None:
    """路径总里程：少于两点为 0；两点等于两点距离；多点等于逐段之和；两实现一致。"""
    assert compute.path_length_km([]) == 0.0
    assert compute.path_length_km([(36.6, 101.7)]) == 0.0

    a, b, c = (36.617, 101.778), (36.897, 100.188), (36.489, 101.569)
    single = compute.path_length_km([a, b])
    assert single == pytest.approx(compute.haversine_km(*a, *b))

    path = compute.path_length_km([a, b, c])
    expected = compute.haversine_km(*a, *b) + compute.haversine_km(*b, *c)
    assert path == pytest.approx(expected)
    assert path > single

    # Python 回退与封装结果一致
    assert compute.path_length_km([a, b, c]) == pytest.approx(
        compute._py_path_length_km([a, b, c]), rel=1e-9
    )


def test_path_length_cpp_matches_python_when_built() -> None:
    """C++ 扩展已构建时：路径总里程两套实现一致（含空 / 单点边界）。"""
    if not compute._has_cpp("path_length_km"):
        pytest.skip("C++ 扩展未构建或版本过旧（回退 Python 实现），本项跳过")
    cases = [
        [],
        [(36.6, 101.7)],
        [(36.617, 101.778), (36.897, 100.188)],
        [(36.617, 101.778), (36.897, 100.188), (36.489, 101.569), (37.848, 95.257)],
    ]
    for points in cases:
        assert compute.path_length_km(points) == pytest.approx(
            compute._py_path_length_km(points), rel=1e-9
        )
