"""测试夹具。

使用独立的 SQLite 文件库，避免污染开发数据库。
环境变量必须在导入 app 之前设置，因为配置是进程启动时读取并缓存的。
"""

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp(prefix='qh_test_')}/test.db"
# 测试不依赖外部服务：清空 REDIS_URL / MINIO_ENDPOINT（相关能力自动降级；
# 需要真实服务的并发 e2e 见 tests_e2e，用 monkeypatch 的用例自行打桩）。
os.environ["REDIS_URL"] = ""
os.environ["MINIO_ENDPOINT"] = ""
# 气象采集默认走模拟源：单测不连外网（真实源用例各自用 httpx.MockTransport 打桩）。
os.environ["WEATHER_PROVIDER"] = "mock"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.db.session import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

# SQLite 默认不校验外键，会让「删父表忘删子表」这类 bug 在测试里漏网（PostgreSQL 会直接报错）。
# 打开校验，让测试行为与 PostgreSQL 一致（例如删除带停靠点的行程）。
if engine.dialect.name == "sqlite":

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> None:
    """整个测试会话开始前建表一次。"""
    init_db()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class FakeMinio:
    """最小 MinIO 桩：供 files 相关用例打桩（test_files / test_shop 共用）。"""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return True

    def make_bucket(self, bucket: str) -> None:  # pragma: no cover - 桩的占位
        pass

    def put_object(self, bucket, key, data, length=None, content_type=None):  # noqa: ANN001
        self.objects[key] = (data.read(), content_type or "")
        return None

    def get_object(self, bucket, key):  # noqa: ANN001
        data, content_type = self.objects[key]

        class _Resp:
            def stream(self, chunk_size: int):  # noqa: ANN202
                yield data

            def close(self) -> None:
                pass

            def release_conn(self) -> None:
                pass

        return _Resp()

    def remove_object(self, bucket, key):  # noqa: ANN001
        self.objects.pop(key, None)


@pytest.fixture
def fake_minio(monkeypatch: pytest.MonkeyPatch) -> FakeMinio:
    """把 files service 的对象存储客户端替换为内存桩。"""
    from app.modules.files import service as files_service

    fake = FakeMinio()
    monkeypatch.setattr(files_service, "_get_client", lambda: fake)
    return fake


# 最小 PNG 头 + 填充：只要求服务端按 content_type 白名单校验，不解析图片内容
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64

# 下单必填的收货信息（订单测试用固定值）
RECEIVER = {
    "receiver_name": "测试收货人",
    "receiver_phone": "13800000000",
    "receiver_address": "青海省西宁市城西区测试路 1 号",
}
