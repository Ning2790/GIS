"""map 模块：底图配置与点位查询测试。"""

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.modules.travel.models import Attraction


def _seed_point(name: str, lat: float | None, lng: float | None, city: str = "测试市") -> int:
    with SessionLocal() as db:
        attraction = Attraction(
            name=name, city=city, description="点位测试", latitude=lat, longitude=lng
        )
        db.add(attraction)
        db.commit()
        db.refresh(attraction)
        return attraction.id


def test_map_config_is_public(client: TestClient) -> None:
    resp = client.get("/api/v1/map/config")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [layer["key"] for layer in data["layers"]] == ["satellite", "street", "terrain"]
    assert data["default"] == "street"
    assert all("{z}" in layer["url_template"] for layer in data["layers"])
    assert all(layer["attribution"] for layer in data["layers"])


def test_map_points_only_with_coordinates(client: TestClient) -> None:
    _seed_point("测试点位甲", 36.9, 100.1)
    _seed_point("测试无坐标景点", None, None)

    resp = client.get("/api/v1/map/points")
    assert resp.status_code == 200, resp.text
    points = resp.json()["data"]["points"]
    names = [point["name"] for point in points]
    assert "测试点位甲" in names
    assert "测试无坐标景点" not in names
    point = next(p for p in points if p["name"] == "测试点位甲")
    assert point["latitude"] == 36.9
    assert point["longitude"] == 100.1


def test_map_points_bbox_filter(client: TestClient) -> None:
    _seed_point("测试点位乙", 36.5, 100.5)

    # 命中范围
    resp = client.get("/api/v1/map/points", params={"bbox": "100.0,36.0,101.0,37.0"})
    assert any(p["name"] == "测试点位乙" for p in resp.json()["data"]["points"])

    # 范围外
    resp = client.get("/api/v1/map/points", params={"bbox": "90.0,20.0,91.0,21.0"})
    assert all(p["name"] != "测试点位乙" for p in resp.json()["data"]["points"])


def test_map_points_bbox_validation(client: TestClient) -> None:
    assert client.get("/api/v1/map/points", params={"bbox": "1,2,3"}).status_code == 400
    assert client.get("/api/v1/map/points", params={"bbox": "a,b,c,d"}).status_code == 400
    # min >= max 视为非法
    assert (
        client.get("/api/v1/map/points", params={"bbox": "100.0,37.0,101.0,36.0"}).status_code
        == 400
    )
    # 超出经纬度范围
    assert (
        client.get("/api/v1/map/points", params={"bbox": "-200.0,20.0,10.0,30.0"}).status_code
        == 400
    )
