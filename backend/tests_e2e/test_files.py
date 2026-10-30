"""files e2e（真 MinIO）：上传 / 鉴权下载 / 类型拒绝 / license_file 引用。

MinIO 不可用时整文件跳过（普通开发环境不因此阻塞）。
"""

import uuid

import httpx
import pytest

from app.core.config import get_settings
from tests_e2e.helpers import login, register_tourist

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 128


def _minio_ready() -> bool:
    settings = get_settings()
    if not settings.minio_endpoint:
        return False
    try:
        resp = httpx.get(f"http://{settings.minio_endpoint}/minio/health/live", timeout=3)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _minio_ready(), reason="MinIO 不可用（docker compose up -d）")


def test_upload_download_roundtrip_and_permissions(api: httpx.Client) -> None:
    owner = register_tourist(api)
    oh = login(api, owner)
    resp = api.post("/files", files={"file": ("e2e资质.png", PNG_BYTES, "image/png")}, headers=oh)
    assert resp.status_code == 200, resp.text
    file_id = resp.json()["data"]["id"]

    got = api.get(f"/files/{file_id}", headers=oh)
    assert got.status_code == 200
    assert got.content == PNG_BYTES
    assert got.headers["content-type"].startswith("image/png")

    other = register_tourist(api)
    assert api.get(f"/files/{file_id}", headers=login(api, other)).status_code == 404

    bad = api.post(
        "/files", files={"file": ("e2e.exe", b"MZ", "application/octet-stream")}, headers=oh
    )
    assert bad.status_code == 400


def test_license_file_platform_reference_roundtrip(api: httpx.Client) -> None:
    """商户注册引用平台上传的资质文件：存在的通过、不存在 400。"""
    owner = register_tourist(api)
    oh = login(api, owner)
    upload = api.post(
        "/files", files={"file": ("e2e执照.pdf", b"%PDF-1.4 e2e", "application/pdf")}, headers=oh
    ).json()["data"]

    ok_resp = api.post(
        "/auth/register/enterprise",
        json={
            "phone": "138" + uuid.uuid4().hex[:8],
            "password": "E2e123456",
            "license_no": f"E2E-{uuid.uuid4().hex[:8]}",
            "license_file": upload["url"],
        },
    )
    assert ok_resp.status_code == 200, ok_resp.text

    bad_resp = api.post(
        "/auth/register/enterprise",
        json={
            "phone": "138" + uuid.uuid4().hex[:8],
            "password": "E2e123456",
            "license_no": f"E2E-{uuid.uuid4().hex[:8]}",
            "license_file": "/api/v1/files/999999",
        },
    )
    assert bad_resp.status_code == 400
