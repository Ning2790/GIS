"""files 模块（P2）测试：上传校验、鉴权读取、公开图片、503 降级、license_file 受控引用、
图片压缩与缩略图（variant=thumb）。

单元环境无 MinIO（minio_endpoint 为空）：未打桩的用例天然覆盖 503；
其余用例用 conftest 的 fake_minio 打桩服务层。
"""

import uuid
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import PNG_BYTES, FakeMinio
from tests.test_imageops import _image_bytes


def _register(client: TestClient, role: str = "tourist", **extra) -> tuple[str, dict[str, str]]:
    phone = "139" + uuid.uuid4().hex[:8]
    password = "Test123456"
    path = (
        "/api/v1/auth/register/tourist" if role == "tourist" else "/api/v1/auth/register/enterprise"
    )
    payload = {"phone": phone, "password": password, **extra}
    resp = client.post(path, json=payload)
    assert resp.status_code == 200, resp.text
    token = client.post("/api/v1/auth/login", json={"phone": phone, "password": password}).json()[
        "data"
    ]["access_token"]
    return phone, {"Authorization": f"Bearer {token}"}


def test_upload_unavailable_without_minio(client: TestClient) -> None:
    """未配置对象存储时上传返回 503（而不是 500）。"""
    _phone, headers = _register(client)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("资质.png", PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 503
    assert resp.json()["code"] == 50300


def test_upload_and_download_with_permissions(client: TestClient, fake_minio: FakeMinio) -> None:
    _owner, owner_headers = _register(client)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("资质证明.png", PNG_BYTES, "image/png")},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["filename"] == "资质证明.png"
    assert data["size"] == len(PNG_BYTES)
    assert data["url"] == f"/api/v1/files/{data['id']}"

    # 上传者可读，内容一致
    got = client.get(f"/api/v1/files/{data['id']}", headers=owner_headers)
    assert got.status_code == 200
    assert got.content == PNG_BYTES
    assert got.headers["content-type"].startswith("image/png")

    # 他人不可读（按不存在处理，不泄漏）
    _other, other_headers = _register(client)
    assert client.get(f"/api/v1/files/{data['id']}", headers=other_headers).status_code == 404

    # 未登录 401
    assert client.get(f"/api/v1/files/{data['id']}").status_code == 401


def test_upload_rejects_bad_type_and_oversize(
    client: TestClient, fake_minio: FakeMinio, monkeypatch: pytest.MonkeyPatch
) -> None:
    _owner, headers = _register(client)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("脚本.exe", b"MZ", "application/octet-stream")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["msg"]

    # 大小上限：临时调小到 1MB，发送 1MB+1 字节
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "file_max_mb", 1)
    oversized = b"x" * (1024 * 1024 + 1)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("big.png", oversized, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "大小上限" in resp.json()["msg"]


def test_license_file_platform_reference_validated(
    client: TestClient, fake_minio: FakeMinio
) -> None:
    """注册引用平台文件时必须真实存在；外部 URL 字符串保持放行。"""
    _owner, headers = _register(client)
    upload = client.post(
        "/api/v1/files",
        files={"file": ("执照.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=headers,
    ).json()["data"]

    # 引用存在的平台文件 → 注册成功
    resp = client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": "138" + uuid.uuid4().hex[:8],
            "password": "Test123456",
            "license_no": "91330100MA2TEST01",
            "license_file": upload["url"],
        },
    )
    assert resp.status_code == 200, resp.text

    # 引用不存在的平台文件 → 400
    resp = client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": "138" + uuid.uuid4().hex[:8],
            "password": "Test123456",
            "license_no": "91330100MA2TEST02",
            "license_file": "/api/v1/files/999999",
        },
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["msg"]

    # 外部 URL 字符串（非平台格式）保持放行
    resp = client.post(
        "/api/v1/auth/register/enterprise",
        json={
            "phone": "138" + uuid.uuid4().hex[:8],
            "password": "Test123456",
            "license_no": "91330100MA2TEST03",
            "license_file": "https://example.com/license.pdf",
        },
    )
    assert resp.status_code == 200, resp.text


def test_public_image_readable_by_anyone(client: TestClient, fake_minio: FakeMinio) -> None:
    """公开图片（商品图）：任何人（含未登录）可读；响应带 is_public。"""
    _owner, owner_headers = _register(client)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("商品主图.png", PNG_BYTES, "image/png")},
        data={"public": "true"},
        headers=owner_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["is_public"] is True

    # 未登录可读（商品页 <img> 匿名加载的场景）
    anonymous = client.get(f"/api/v1/files/{data['id']}")
    assert anonymous.status_code == 200
    assert anonymous.content == PNG_BYTES

    # 他人登录也可读
    _other, other_headers = _register(client)
    assert client.get(f"/api/v1/files/{data['id']}", headers=other_headers).status_code == 200


def test_public_flag_rejected_for_non_image(client: TestClient, fake_minio: FakeMinio) -> None:
    """非图片不允许设为公开（防止把资质 PDF 暴露出去）。"""
    _owner, headers = _register(client)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("资质.pdf", b"%PDF-1.4", "application/pdf")},
        data={"public": "true"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "只有图片可以设为公开" in resp.json()["msg"]


def test_private_file_still_requires_owner(client: TestClient, fake_minio: FakeMinio) -> None:
    """默认私有的文件不受影响：未登录 401、他人 404。"""
    _owner, owner_headers = _register(client)
    file_id = client.post(
        "/api/v1/files",
        files={"file": ("私有.png", PNG_BYTES, "image/png")},
        headers=owner_headers,
    ).json()["data"]["id"]

    resp = client.get(f"/api/v1/files/{file_id}")
    assert resp.status_code == 401
    _other, other_headers = _register(client)
    assert client.get(f"/api/v1/files/{file_id}", headers=other_headers).status_code == 404


def _upload_image(
    client: TestClient,
    headers: dict[str, str],
    data: bytes,
    *,
    public: bool = False,
    name: str = "商品图.jpg",
) -> dict:
    resp = client.post(
        "/api/v1/files",
        files={"file": (name, data, "image/jpeg")},
        data={"public": "true"} if public else None,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_image_upload_compressed_with_thumbnail(client: TestClient, fake_minio: FakeMinio) -> None:
    """大图上传：原图被压缩、生成缩略图，元数据给出压缩前后大小与缩略图地址。"""
    _owner, headers = _register(client)
    data = _image_bytes((2400, 1800))
    payload = _upload_image(client, headers, data, public=True)

    # 元数据：size 为入库大小（已压缩）、original_size 为上传原始大小
    assert payload["original_size"] == len(data)
    assert payload["size"] < len(data)
    assert payload["url"] == f"/api/v1/files/{payload['id']}"
    assert payload["thumbnail_url"] == f"/api/v1/files/{payload['id']}?variant=thumb"

    # 对象存储里真的存了两个对象：压缩后的原图 + 缩略图
    stored = [k for k in fake_minio.objects if k.startswith("uploads/")]
    assert len(stored) == 2
    thumbs = [k for k in stored if ".thumb" in k]
    assert len(thumbs) == 1

    # 原图：长边 ≤ IMAGE_MAX_EDGE（1600），内容类型不变
    original = client.get(payload["url"])
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("image/jpeg")
    assert len(original.content) == payload["size"]
    with Image.open(BytesIO(original.content)) as image:
        assert max(image.size) == 1600

    # 缩略图：长边 ≤ IMAGE_THUMBNAIL_EDGE（400），且比原图小
    thumb = client.get(payload["thumbnail_url"])
    assert thumb.status_code == 200
    assert thumb.headers["content-type"].startswith("image/jpeg")
    assert len(thumb.content) < len(original.content)
    with Image.open(BytesIO(thumb.content)) as image:
        assert max(image.size) == 400


def test_thumbnail_variant_falls_back_to_original(
    client: TestClient, fake_minio: FakeMinio
) -> None:
    """不可解码的「图片」（只有头）：metadata 不给缩略图地址，服务端 variant=thumb 回退原图。"""
    _owner, headers = _register(client)
    payload = _upload_image(client, headers, PNG_BYTES, name="伪造.png")
    assert payload["original_size"] is None  # 没被处理过（原样入库）
    assert payload["thumbnail_url"] is None  # 没生成就不报地址（前端按此回退原图）

    # 即便直接请求缩略图参数，也回退原图而不是 404（老客户端 / 已缓存地址仍可用）
    thumb = client.get(f"{payload['url']}?variant=thumb", headers=headers)
    assert thumb.status_code == 200
    assert thumb.content == PNG_BYTES


def test_thumbnail_object_missing_falls_back_to_original(
    client: TestClient, fake_minio: FakeMinio
) -> None:
    """缩略图对象被清理（DB 与存储不一致）时：读取自动回退原图，不返回裂图。"""
    _owner, headers = _register(client)
    payload = _upload_image(client, headers, _image_bytes((800, 600)))
    assert payload["thumbnail_url"] is not None

    # 模拟对象被人工清理 / 快照回滚：只删缩略图对象
    thumb_key = next(key for key in fake_minio.objects if ".thumb" in key)
    fake_minio.objects.pop(thumb_key)

    resp = client.get(payload["thumbnail_url"], headers=headers)
    assert resp.status_code == 200
    assert len(resp.content) == payload["size"]  # 回退的是原图


def test_non_image_has_no_thumbnail_url(client: TestClient, fake_minio: FakeMinio) -> None:
    """PDF 等非图片：缩略图地址为 null，original_size 为 null（无压缩概念）。"""
    _owner, headers = _register(client)
    resp = client.post(
        "/api/v1/files",
        files={"file": ("执照.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()["data"]
    assert payload["thumbnail_url"] is None
    assert payload["original_size"] is None
    assert payload["size"] == len(b"%PDF-1.4 fake")


def test_variant_param_is_validated(client: TestClient, fake_minio: FakeMinio) -> None:
    _owner, headers = _register(client)
    payload = _upload_image(client, headers, _image_bytes((300, 200)))
    resp = client.get(f"{payload['url']}?variant=huge")
    assert resp.status_code == 422


def test_private_image_thumbnail_keeps_permissions(
    client: TestClient, fake_minio: FakeMinio
) -> None:
    """私有图片的缩略图同样受鉴权约束（不能借缩略图绕过权限）。"""
    _owner, headers = _register(client)
    payload = _upload_image(client, headers, _image_bytes((800, 600)), name="私有.jpg")

    assert client.get(payload["thumbnail_url"]).status_code == 401  # 未登录
    _other, other_headers = _register(client)
    assert client.get(payload["thumbnail_url"], headers=other_headers).status_code == 404
    assert client.get(payload["thumbnail_url"], headers=headers).status_code == 200


def test_private_file_with_invalid_token_still_401(
    client: TestClient, fake_minio: FakeMinio
) -> None:
    """可选登录容错后，私有文件的鉴权不受影响：无效令牌仍按未认证处理。"""
    _owner, owner_headers = _register(client)
    file_id = client.post(
        "/api/v1/files",
        files={"file": ("私有令牌.png", PNG_BYTES, "image/png")},
        headers=owner_headers,
    ).json()["data"]["id"]

    bad = {"Authorization": "Bearer not-a-real-token"}
    assert client.get(f"/api/v1/files/{file_id}", headers=bad).status_code == 401

    # 公开图片带无效令牌仍可读（公开内容不因令牌问题变错误页）
    public_id = client.post(
        "/api/v1/files",
        files={"file": ("公开令牌.png", PNG_BYTES, "image/png")},
        data={"public": "true"},
        headers=owner_headers,
    ).json()["data"]["id"]
    assert client.get(f"/api/v1/files/{public_id}", headers=bad).status_code == 200
