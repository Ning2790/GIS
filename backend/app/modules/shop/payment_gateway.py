"""支付网关适配层（N13）：把「支付单占位」与「第三方网关」解耦。

平台不做资金池：`payments` 表只记录状态与第三方单号，真正收款由第三方完成。
本模块定义**协议**（`PaymentGateway`）与**占位实现**（`MockGateway`，复刻既有的
「管理员模拟回调」行为，不引入任何行为变化）；接支付宝 / 微信时实现同一协议、
在 `.env` 切 `PAYMENT_GATEWAY` 即可，业务代码（service / router）零改动。

真实网关要做的三件事（Mock 直通，但公开语义已经定好）：
1. `create_payment`：向第三方下单，返回**支付链接 / 二维码**（`GatewayPayment.pay_url`）；
2. `verify_notify`：对回调做**验签**（Mock 恒真——**因此 mock 模式下不暴露公网回调端点**，
   否则任何人都能标记支付成功；见 `docs/部署.md` 的接入说明）；
3. `parse_notify`：把回调字段归一成 `NormalizedCallback`（本地单号 / 流水号 / 成败）。

接真实网关还需要新增一个持久列（文档已列）：**第三方单号 `out_trade_no`** 要在创建支付单时
落库，回调才能可靠定位到本地支付单（当前 mock 用 `mock-<payment_id>` 编码在单号里）。
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

from app.core.config import get_settings
from app.core.errors import BadRequestError

MOCK_OUT_TRADE_NO_PREFIX = "mock-"


@dataclass(frozen=True)
class GatewayPayment:
    """网关创建支付单的结果。占位实现没有支付链接（前端下单后仍走管理员模拟回调）。"""

    out_trade_no: str
    pay_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedCallback:
    """回调归一化结果（真实网关验签 + 字段映射后产出）。"""

    out_trade_no: str
    success: bool
    trade_no: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentGateway(Protocol):
    """支付网关协议：三个方法覆盖「下单 → 回调验签 → 回调解析」全流程。"""

    name: str

    def create_payment(
        self, *, payment_id: int, order_id: int, amount: Decimal, subject: str
    ) -> GatewayPayment: ...

    def verify_notify(self, *, headers: Mapping[str, str], body: bytes) -> bool: ...

    def parse_notify(self, *, headers: Mapping[str, str], body: bytes) -> NormalizedCallback: ...


class MockGateway:
    """占位网关：复刻既有行为——无支付链接、回调由管理员在控制台触发。"""

    name = "mock"

    def create_payment(
        self, *, payment_id: int, order_id: int, amount: Decimal, subject: str
    ) -> GatewayPayment:
        # 单号里编码本地支付单 id，回调（或测试）据此定位；真实网关由第三方生成
        return GatewayPayment(out_trade_no=f"{MOCK_OUT_TRADE_NO_PREFIX}{payment_id}")

    def verify_notify(self, *, headers: Mapping[str, str], body: bytes) -> bool:
        """Mock 无签名可验：恒真。**因此 mock 模式不开放公网回调端点**（见模块文档）。"""
        return True

    def parse_notify(self, *, headers: Mapping[str, str], body: bytes) -> NormalizedCallback:
        """解析 JSON 回调体（真实网关在这里做字段映射，如 alipay 的 trade_status）。"""
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BadRequestError("回调报文格式不正确") from exc
        if not isinstance(payload, dict):
            raise BadRequestError("回调报文格式不正确")
        out_trade_no = payload.get("out_trade_no")
        if not out_trade_no:
            raise BadRequestError("回调缺少 out_trade_no")
        return NormalizedCallback(
            out_trade_no=str(out_trade_no),
            success=bool(payload.get("success")),
            trade_no=payload.get("trade_no"),
            raw=payload,
        )


def payment_id_from_out_trade_no(out_trade_no: str) -> int | None:
    """从网关单号解析本地支付单 id（mock 约定）；解析不出返回 None。"""
    if not out_trade_no.startswith(MOCK_OUT_TRADE_NO_PREFIX):
        return None
    suffix = out_trade_no[len(MOCK_OUT_TRADE_NO_PREFIX) :]
    return int(suffix) if suffix.isdigit() else None


def get_gateway() -> PaymentGateway:
    """按配置取网关实现；未知名称直接报错（与 llm.chat / embed_texts 的口径一致）。"""
    name = get_settings().payment_gateway
    if name == "mock":
        return MockGateway()
    raise RuntimeError(
        f"未知的 PAYMENT_GATEWAY：{name}（当前仅内置 mock；接真实网关见 docs/部署.md）"
    )
