"""上游分布探针（对照实验用，N9 遗留问题：「轮询下为何总集中在一台」）。

用途：对网关（或任意 HTTP 端点）打一段**可控并发**的负载，输出：
- 总请求数 / 状态码直方图 / 吞吐；
- 每秒请求数（观察是否为稳定流）；
- 失败时的错误类型（拒绝 = 客户端侧连接失败等）。

配合网关访问日志（`$upstream_addr`）即可统计每个上游实例的请求数与 503 数——
这正是「拒绝是否集中在某一台」的直接证据。

用法（backend 目录）：
    uv run python scripts/upstream_probe.py --url http://127.0.0.1:9080/api/v1/shop/products \
        --concurrency 60 --duration 45

只依赖 httpx（项目依赖），不引入压测框架：本探针关注的是**分布**而不是极限容量，
所以刻意用"固定并发 + 定时长"的简单模型（Locust 的三档压测见 scripts/loadtest.py）。
"""

import argparse
import asyncio
import time
from collections import Counter

import httpx


async def worker(
    client: httpx.AsyncClient,
    url: str,
    deadline: float,
    statuses: Counter,
    per_second: Counter,
    exceptions: Counter,
) -> None:
    """一个并发位的循环：每次请求计一个状态码；**只有客户端异常**单独计。

    注意：4xx/5xx 是服务端响应（过载实验要测的正是 503），不要重复计进总量——
    否则 total / 吞吐会虚增（复审实测过：全 503 的 mock 下总请求被算了两次）。
    """
    while time.monotonic() < deadline:
        try:
            response = await client.get(url)
            statuses[response.status_code] += 1
        except Exception as exc:  # noqa: BLE001 - 客户端侧失败（连接被拒 / 超时等）
            exceptions[type(exc).__name__] += 1
        per_second[int(time.time())] += 1


async def main() -> None:
    parser = argparse.ArgumentParser(description="上游分布探针（固定并发 + 定时长）")
    parser.add_argument("--url", required=True, help="目标 URL（网关入口）")
    parser.add_argument("--concurrency", type=int, default=60, help="并发请求数")
    parser.add_argument(
        "--duration",
        type=float,
        default=45.0,
        help="持续秒数（**软上限**：到点后不再发新请求，但会等最后一个在途请求结束，"
        "所以打印的用时可略超该值，最多再等一个 --timeout）",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="单请求超时（秒）")
    args = parser.parse_args()

    statuses: Counter = Counter()
    per_second: Counter = Counter()
    exceptions: Counter = Counter()

    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        # 预热：建连与缓存（不计数）
        await client.get(args.url)
        deadline = time.monotonic() + args.duration
        started = time.time()
        await asyncio.gather(
            *[
                worker(client, args.url, deadline, statuses, per_second, exceptions)
                for _ in range(args.concurrency)
            ]
        )
        elapsed = time.time() - started

    # 总量 = 服务端响应数 + 客户端异常数（不重复计 4xx/5xx）
    total = sum(statuses.values()) + sum(exceptions.values())
    print(f"总请求 {total}（预热 1 次不计），用时 {elapsed:.1f}s，吞吐 {total / elapsed:.1f} req/s")
    print("状态码：", dict(sorted(statuses.items())))
    http_errors = sum(count for code, count in statuses.items() if code >= 400)
    if http_errors:
        print(f"其中 HTTP 错误状态 {http_errors} 次（服务端已响应，如过载 503）")
    if exceptions:
        print("客户端侧异常：", dict(exceptions))
    rates = [per_second[second] for second in sorted(per_second)]
    if rates:
        print(
            f"每秒请求数：min={min(rates)} max={max(rates)} "
            f"avg={sum(rates) / len(rates):.0f}（共 {len(rates)} 秒）"
        )


if __name__ == "__main__":
    asyncio.run(main())
