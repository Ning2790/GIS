"""知识检索（N12）：向量 + 关键词**合并**，双路径都不丢。

检索流程（`retrieve`）：
1. 读知识分块表（`ai_knowledge_chunks`，向量在 JSON 列里）；
2. 向量路径：对问题做嵌入（`app/core/rag.py`），与每条向量算余弦，取 ≥ `RAG_MIN_SCORE` 的；
3. 关键词路径：原有命中数打分（精确信号，命中 ≥1 条即返回）；
4. **两路结果按主题合并**（复审发现的修法）：只走向量会让「向量误命中」挤掉关键词的正确结果
   （实测「需要带什么衣服」曾命中「特产」而丢掉本该命中的「装备」），所以合并时
   主题在两条路径都出现的最优先，其次按归一化分数排序；
5. 任何异常（表不存在 / 嵌入服务不可用 / 维度不一致）都不向调用方抛：记日志后退化为关键词。

表为空时直接用内置知识（`knowledge_data.py`）做关键词回退——这是「无向量环境回退不报错」
的实现方式，也是种子脚本没跑过时的保底路径。
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import rag
from app.core.config import get_settings
from app.modules.ai.knowledge_data import KNOWLEDGE_ENTRIES
from app.modules.ai.models import KnowledgeChunk

logger = logging.getLogger(__name__)

_EXCERPT_LIMIT = 80
_KEYWORD_SCORE_CAP = 3.0  # 关键词命中数上限（用于与余弦分归一后比较）
_dim_warned = False  # 维度/模型不一致只告警一次，避免刷日志


@dataclass
class KnowledgeHit:
    """一条命中：topic + 分数/命中方式 + 摘要（前端来源卡片与 prompt 都用它）。

    matched：关键词路径命中的关键词（展示门禁用它判断"这个词本身够不够具体"，
    如「无人机」「水上雅丹」这类 3 字以上的词命中一次就是强信号）。
    """

    topic: str
    content: str
    score: float
    matched_by: str  # vector | keyword
    matched: tuple[str, ...] = ()

    @property
    def excerpt(self) -> str:
        text = self.content.strip()
        return text if len(text) <= _EXCERPT_LIMIT else text[: _EXCERPT_LIMIT - 1] + "…"


def _keyword_hits(question: str, limit: int) -> list[KnowledgeHit]:
    """关键词打分（命中数降序），作为精确信号与兜底路径。"""
    scored: list[tuple[int, int, dict, tuple[str, ...]]] = []
    for index, entry in enumerate(KNOWLEDGE_ENTRIES):
        matched = tuple(keyword for keyword in entry["keywords"] if keyword in question)
        if matched:
            scored.append((len(matched), index, entry, matched))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        KnowledgeHit(
            topic=entry["topic"],
            content=entry["content"],
            score=float(score),
            matched_by="keyword",
            matched=matched,
        )
        for score, _index, entry, matched in scored[:limit]
    ]


def _load_chunks(db: Session) -> list[KnowledgeChunk]:
    return list(db.scalars(select(KnowledgeChunk).order_by(KnowledgeChunk.topic)))


def embed_text(text: str) -> list[float]:
    """对单条文本做嵌入（seed 脚本与检索共用，保证口径一致）。"""
    return rag.embed_texts([text])[0]


def entry_text(entry: dict) -> str:
    """知识条目的嵌入文本形态：主题｜关键词｜正文（seed 与检索口径必须一致）。"""
    return f"{entry['topic']}｜{' '.join(entry['keywords'])}｜{entry['content']}"


def _vector_hits(db: Session, question: str, limit: int) -> list[KnowledgeHit]:
    """向量路径；任何异常（含维度/模型不一致）都返回空列表并记日志，由关键词兜底。"""
    global _dim_warned
    settings = get_settings()
    chunks = _load_chunks(db)
    if not chunks:
        return []
    expected_dim = len(embed_text("维度探测"))
    mismatched = [
        chunk
        for chunk in chunks
        if (chunk.embedding_dim and chunk.embedding_dim != expected_dim)
        or (chunk.embedding_provider and chunk.embedding_provider != settings.embedding_provider)
        or (
            settings.embedding_model
            and chunk.embedding_model
            and chunk.embedding_model != settings.embedding_model
        )
    ]
    if mismatched and not _dim_warned:
        _dim_warned = True
        logger.warning(
            "知识向量与当前嵌入配置不一致（%d/%d 条）：已跳过向量检索、回退关键词；"
            "请重跑 `uv run python scripts/seed_knowledge.py` 重算向量",
            len(mismatched),
            len(chunks),
        )
    usable = [chunk for chunk in chunks if chunk not in mismatched]
    if not usable:
        return []

    question_vector = embed_text(question)
    scored = [
        (rag.cosine_similarity(question_vector, chunk.embedding or []), chunk) for chunk in usable
    ]
    scored = [item for item in scored if item[0] >= settings.rag_min_score]
    scored.sort(key=lambda item: (-item[0], item[1].topic))
    return [
        KnowledgeHit(
            topic=chunk.topic, content=chunk.content, score=round(score, 4), matched_by="vector"
        )
        for score, chunk in scored[:limit]
    ]


def retrieve(db: Session, question: str, *, limit: int | None = None) -> list[KnowledgeHit]:
    """检索知识：向量 + 关键词合并；任何异常都不向调用方抛（保底可用）。"""
    top_k = limit or get_settings().rag_top_k
    keyword_hits = _keyword_hits(question, top_k)
    vector_hits: list[KnowledgeHit] = []
    try:
        vector_hits = _vector_hits(db, question, top_k)
    except Exception as exc:  # 表不存在 / 连接异常 / 嵌入服务不可用：回退关键词
        logger.warning("向量检索不可用，回退关键词检索：%s", exc)

    merged: dict[str, KnowledgeHit] = {}
    for hit in keyword_hits:  # 关键词是精确信号，先占位
        merged[hit.topic] = hit
    for hit in vector_hits:
        # 两路都命中的主题：用向量分展示（点开卡片能看到相似度），但仍算「双重命中」
        merged.setdefault(hit.topic, hit)
    both_topics = {hit.topic for hit in keyword_hits} & {hit.topic for hit in vector_hits}

    def sort_key(hit: KnowledgeHit) -> tuple[int, float]:
        raw = hit.score if hit.matched_by == "vector" else hit.score / _KEYWORD_SCORE_CAP
        return (1 if hit.topic in both_topics else 0, raw)

    return sorted(merged.values(), key=sort_key, reverse=True)[:top_k]


def mentioned_topics(question: str) -> set[str]:
    """问题里**明确提到**的条目：按条目首关键词（地点 / 主题名）匹配。

    用于展示门禁的「跨地点互斥」——用户明确问了某个已知地点时，
    纯向量相似的**另一个地点**不进来源卡片（复审实测：问「青海湖油菜花」
    会被推到「门源油菜花」，属跨地点误导）。
    """
    return {
        entry["topic"]
        for entry in KNOWLEDGE_ENTRIES
        if entry["keywords"] and entry["keywords"][0] in question
    }


def strong_hits(hits: list[KnowledgeHit], *, question: str = "") -> list[KnowledgeHit]:
    """展示用命中：首位始终保留，非首位要求更强信号（见 RAG_SECONDARY_MIN_SCORE）。

    复审延续项：天气问题的第二、三条命中（装备 0.35 / 亲子 0.29）属于「相关但弱」，
    放进 prompt 有益、放进来源卡片会误导；检索本身（prompt 上下文）仍返回全部 top_k。

    question 非空时启用**跨地点互斥**：用户明确提到的地点之外的「纯向量命中」
    不进卡片（关键词命中不受影响——关键词是精确信号）。
    """
    threshold = get_settings().rag_secondary_min_score
    mentioned = mentioned_topics(question) if question else set()
    kept: list[KnowledgeHit] = []
    for index, hit in enumerate(hits):
        if index == 0:
            kept.append(hit)
            continue
        if hit.matched_by == "vector" and mentioned and hit.topic not in mentioned:
            continue  # 跨地点互斥：用户问的是别的已知地点，纯相似不足以进卡片
        if hit.matched_by == "keyword":
            # 关键词强信号：命中 ≥2 个词，或命中的词本身够具体（≥3 字，如「无人机」
            # 「水上雅丹」）——扩充知识库后单词命中很常见，只按词数过滤会把
            # 「问无人机 → 环保与无人机」这类最贴切的条目挡在卡片外（实测踩到）。
            if not hit.matched:
                # 关键词命中却没带命中词（构造异常）：记一次告警，避免静默退回旧规则
                logger.warning("关键词命中缺少 matched（%s）：按旧规则判定", hit.topic)
            strong = hit.score >= 2 or any(len(keyword) >= 3 for keyword in hit.matched)
        else:
            strong = hit.score >= threshold  # 向量分是余弦相似度
        if strong:
            kept.append(hit)
    return kept


def build_context(hits: list[KnowledgeHit]) -> str:
    """把命中拼成 prompt 里的一段（与原有【平台知识】格式保持一致）。"""
    return "\n".join(f"- {hit.topic}：{hit.content}" for hit in hits)


def upsert_entries(db: Session) -> tuple[int, int]:
    """按 topic 幂等写入内置知识并重算向量，返回 (新增, 更新)。

    seed 脚本与测试共用这一份实现（避免两处漂移）；并发执行时唯一约束冲突按
    「另一实例已完成」处理——重查后转更新，不抛给调用方。
    """
    settings = get_settings()
    vectors = rag.embed_texts([entry_text(entry) for entry in KNOWLEDGE_ENTRIES])
    created = updated = 0
    for entry, vector in zip(KNOWLEDGE_ENTRIES, vectors, strict=True):
        chunk = db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.topic == entry["topic"]))
        if chunk is None:
            chunk = KnowledgeChunk(topic=entry["topic"], content="", keywords=[], embedding=[])
            db.add(chunk)
            created += 1
        else:
            updated += 1
        chunk.content = entry["content"]
        chunk.keywords = list(entry["keywords"])
        chunk.embedding = vector
        chunk.embedding_provider = settings.embedding_provider
        chunk.embedding_model = settings.embedding_model
        chunk.embedding_dim = len(vector)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # 并发实例已写入；重查后逐条转更新
        logger.warning("知识写入撞唯一约束（疑似并发 seed），改为更新")
        for entry, vector in zip(KNOWLEDGE_ENTRIES, vectors, strict=True):
            chunk = db.scalar(select(KnowledgeChunk).where(KnowledgeChunk.topic == entry["topic"]))
            if chunk is None:
                continue
            chunk.content = entry["content"]
            chunk.keywords = list(entry["keywords"])
            chunk.embedding = vector
            chunk.embedding_provider = settings.embedding_provider
            chunk.embedding_model = settings.embedding_model
            chunk.embedding_dim = len(vector)
        db.commit()
    return created, updated
