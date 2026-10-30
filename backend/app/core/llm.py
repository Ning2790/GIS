"""大模型调用统一入口。

业务模块一律通过这里调用模型，不要再自行发 HTTP。

默认 mock 提供方：无需密钥与 GPU 即可跑通全链路（本地与 CI 都靠它）。
接入云端只改 .env（代码零改动）：

    AI_PROVIDER=openai
    AI_BASE_URL=https://<兼容 OpenAI 协议的地址>/v1
    AI_API_KEY=<密钥>
    AI_MODEL=<模型名>
"""

import httpx

from app.core.config import get_settings

MOCK_PREFIX = "（AI 助手 · mock）"


def chat(messages: list[dict[str, str]], *, temperature: float = 0.7) -> str:
    """对话补全，返回助手回复文本。

    messages 形如 [{"role": "system"|"user"|"assistant", "content": "..."}]。
    调用失败时抛出异常，由业务方决定降级策略。
    """
    settings = get_settings()
    if settings.ai_provider == "mock":
        return _mock_reply(messages)
    if settings.ai_provider == "openai":
        return _openai_chat(messages, temperature=temperature)
    raise RuntimeError(f"未知的 AI_PROVIDER：{settings.ai_provider}")


def _mock_reply(messages: list[dict[str, str]]) -> str:
    """mock 回复：确定性、无外部依赖，便于本地与 CI 验证全链路。"""
    last_user = next(
        (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
    )
    snippet = last_user.strip()[:60]
    return (
        f"{MOCK_PREFIX}已收到您的问题：{snippet}。"
        "当前为本地模拟回复，接入大模型后将自动生成正式回答。"
    )


def _openai_chat(messages: list[dict[str, str]], *, temperature: float) -> str:
    """兼容 OpenAI 协议（vLLM / Ollama / 云端）的对话补全。"""
    settings = get_settings()
    resp = httpx.post(
        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        json={
            "model": settings.ai_model,
            "messages": messages,
            "temperature": temperature,
        },
        timeout=settings.ai_timeout_seconds,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
