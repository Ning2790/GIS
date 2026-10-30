"""导出 OpenAPI 契约。

用法（在 backend 目录下）：
    uv run python scripts/export_openapi.py

产物：docs/api/openapi.json —— 前后端共同的接口契约，前端据此对齐字段。
后端任何接口改动都应重新导出并提交，评审时一并检查。
"""

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402

TARGET = BACKEND_ROOT.parent / "docs" / "api" / "openapi.json"

TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OpenAPI 已导出：{TARGET}")
