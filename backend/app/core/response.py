"""统一响应信封。

前后端一律以 {code, msg, data} 结构交互：
- code == 0 表示成功，data 为业务数据；
- code != 0 表示失败，msg 为可直接展示给用户的提示。

接口实现统一用 ok() 返回，不要自行拼字典。
"""

from typing import Any


def ok(data: Any = None, msg: str = "ok") -> dict[str, Any]:
    """成功响应。"""
    return {"code": 0, "msg": msg, "data": data}


def fail(code: int, msg: str, data: Any = None) -> dict[str, Any]:
    """失败响应。仅异常处理器使用。"""
    return {"code": code, "msg": msg, "data": data}
