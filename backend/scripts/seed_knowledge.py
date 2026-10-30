"""把内置知识写入向量检索表（N12，幂等）。

用法（backend 目录，可重复执行）：
    uv run python scripts/seed_knowledge.py

实现复用 `app.modules.ai.knowledge.upsert_entries`（与测试同一份逻辑）：按 `topic` upsert，
向量由 `app/core/rag.py` 的嵌入实现生成；**换了嵌入模型 / 改了 EMBEDDING_DIM 必须重跑本脚本**
（向量与配置不一致时检索会跳过向量、退化为关键词，并打一条 warning）。
"""

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.modules.ai import knowledge  # noqa: E402
from app.modules.ai.knowledge_data import KNOWLEDGE_ENTRIES  # noqa: E402


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        created, updated = knowledge.upsert_entries(db)
    dimension = len(knowledge.embed_text("维度探测"))
    print(f"知识分块已就绪：新增 {created} 条、更新 {updated} 条（共 {len(KNOWLEDGE_ENTRIES)} 条）")
    print(f"嵌入实现：{settings.embedding_provider}（维度 {dimension}）")


if __name__ == "__main__":
    main()
