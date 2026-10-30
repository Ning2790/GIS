"""限流 e2e（真 Redis）：超限返回 429 统一信封 + Retry-After。

与单元测试的区别：这里走真实 HTTP + 真 Redis 计数（验证键、窗口与装配
在真实链路里生效）；阈值通过同进程的 settings 单例临时调小。
"""

import time

import httpx

from tests_e2e.helpers import login, register_tourist


def test_ai_rate_limit_429(api: httpx.Client, monkeypatch) -> None:
    from app.core.config import get_settings

    # 避免恰好在窗口边界开始导致计数跨窗重置（最多等 5 秒）
    if int(time.time()) % 60 > 55:
        time.sleep(61 - int(time.time()) % 60)

    monkeypatch.setattr(get_settings(), "rate_limit_ai_per_minute", 2)
    tourist = register_tourist(api)
    th = login(api, tourist)

    codes = [
        api.post("/ai/ask", headers=th, json={"question": "限流验证"}).status_code for _ in range(3)
    ]
    assert codes == [200, 200, 429]

    resp = api.post("/ai/ask", headers=th, json={"question": "限流验证"})
    assert resp.status_code == 429
    assert resp.json()["code"] == 42900
    assert int(resp.headers["Retry-After"]) >= 1
