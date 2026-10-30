"""嵌入与相似度（N12）：向量检索的公共件。

设计（用户拍板）：**载体 = JSONB 存向量 + 应用层算余弦**（本项目的知识库规模是
十几条，向量检索的瓶颈在语义而非数据量）；**嵌入默认 mock 确定性实现**，不依赖
外网与密钥，测试与演示可复现；接真实嵌入模型只改 `.env`（`EMBEDDING_PROVIDER=openai`
+ `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL`）。

mock 实现不是随机数：它把文本切成词元 → 用同义词表归一（如「小孩/儿童/亲子」同桶）
→ 哈希装袋成 `embedding_dim` 维向量并做 L2 归一化。这样**近义表达会得到相近向量**，
足以演示「关键词匹配不到、语义能匹配到」的差别；真实语义泛化仍需换真嵌入模型。
"""

import hashlib
import math
import re

import httpx

from app.core.config import get_settings

# 同义词归并表：key 是任意一种说法，value 是归一后的词元。
# 只覆盖本项目知识库与游客常见问法的交集，不做通用词典。
SYNONYMS: dict[str, str] = {}
for _group, _terms in {
    "高原反应": ["高反", "高原反应", "缺氧", "头痛", "头晕", "氧气", "红景天", "海拔反应", "高原"],
    # 「初到高原」类问法（评测里「到青海第一天该注意什么」曾漏招）
    "初到": ["第一天", "初到", "刚到", "抵达", "头一天", "落地"],
    "儿童": ["小孩", "孩子", "儿童", "宝宝", "亲子", "带娃", "小朋友", "婴儿", "幼儿"],
    "季节": ["季节", "几月", "什么时候", "最佳时间", "月份", "花期", "油菜花"],
    "费用": ["费用", "价格", "多少钱", "预算", "花费", "门票价"],
    "住宿": ["住宿", "酒店", "民宿", "住哪", "客栈"],
    "交通": ["交通", "怎么去", "自驾", "包车", "拼车", "路况", "火车", "大巴"],
    "天气": ["天气", "气温", "冷", "热", "下雨", "防晒", "紫外线", "保暖"],
    "证件": ["证件", "身份证", "边防证", "护照", "通行证"],
    "特产": ["特产", "伴手礼", "买什么", "邮寄", "快递", "牦牛肉", "雪菊"],
    "售后": ["售后", "退款", "退货", "换货", "质量问题", "包装破损"],
    "装备": ["带什么", "装备", "行李", "穿什么", "衣服"],
    "青海湖": ["青海湖", "环湖", "环湖公路", "二郎剑", "黑马河"],
    "宠物": ["宠物", "带狗", "带猫", "狗狗"],
}.items():
    for _term in _terms:
        SYNONYMS[_term] = _group

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,4}|[a-zA-Z]+|\d+")
_MOCK_PREFIX = "mock:"
_SYNONYM_WEIGHT = 3  # 命中同义词组时的词元权重（放大语义信号，压过字形噪声）


def _tokens(text: str) -> list[str]:
    """切词元：先扫同义词表（长词优先、命中即归一并加权），余下按字符 2-gram 补字形信号。"""
    lowered = text.lower()
    tokens: list[str] = []
    for term in sorted(SYNONYMS, key=len, reverse=True):
        if term in lowered:
            tokens.extend([SYNONYMS[term]] * _SYNONYM_WEIGHT)
            lowered = lowered.replace(term, " ")
    for chunk in lowered.split():
        ascii_words = [match.group() for match in _TOKEN_RE.finditer(chunk)]
        if chunk.isascii():
            tokens.extend(ascii_words or [chunk])
            continue
        # 只用 2/3-gram：单字词元会与任意长文本产生大量稀疏重叠（实测造成假阳性），
        # 极短问句（如「高反」）本就靠同义词组命中，不依赖单字
        for size in (2, 3):
            tokens.extend(chunk[i : i + size] for i in range(len(chunk) - size + 1))
    return [token for token in tokens if token.strip()]


def mock_embed(text: str, *, dim: int | None = None) -> list[float]:
    """确定性 mock 嵌入：同义词归一 + **非负**哈希词袋 + L2 归一化（同文本恒等）。

    用非负计数而不是带符号哈希：带符号会让无关文本之间出现随机正负相关，
    反而盖过同义信号（初版实测「带小孩…」与「亲子出行…」相似度 -0.08，低于无关句）。
    """
    size = dim or get_settings().embedding_dim
    vector = [0.0] * size
    for token in _tokens(text):
        digest = hashlib.sha1(f"{_MOCK_PREFIX}{token}".encode()).digest()
        index = int.from_bytes(digest[:4], "big") % size
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def openai_embed(texts: list[str]) -> list[list[float]]:
    """兼容 OpenAI 协议的嵌入接口（vLLM / Ollama / 云端）。**未对真实服务实测**，
    接上后请按 `docs/部署.md` 的说明做一次端到端验证。"""
    settings = get_settings()
    resp = httpx.post(
        f"{settings.embedding_base_url.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        json={"model": settings.embedding_model, "input": texts},
        timeout=settings.embedding_timeout_seconds,
    )
    resp.raise_for_status()
    payload = resp.json()
    return [item["embedding"] for item in payload["data"]]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """按配置选择嵌入实现；未知 provider 直接报错（与 llm.chat 的口径一致）。"""
    settings = get_settings()
    if settings.embedding_provider == "mock":
        return [mock_embed(text) for text in texts]
    if settings.embedding_provider == "openai":
        return openai_embed(texts)
    raise RuntimeError(f"未知的 EMBEDDING_PROVIDER：{settings.embedding_provider}")


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """余弦相似度（向量已归一化时等于点积；此处仍做完整计算以防外部向量未归一）。"""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)
