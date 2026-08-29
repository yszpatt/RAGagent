from functools import lru_cache
from app.generation.providers.base import EmbeddingProvider, RerankerProvider, LLMProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker
from app.generation.providers.llm import OllamaLLM, OpenAICompatLLM
from app.core.config import settings


@lru_cache
def get_embedding() -> EmbeddingProvider:
    return BgeM3Embedding(settings.embedding_model)


@lru_cache
def get_reranker() -> RerankerProvider:
    return BgeReranker(settings.reranker_model)


@lru_cache
def get_llm() -> LLMProvider:
    """按配置实例化 LLM。

    LLM_PROVIDER=openai_compat 时走 /v1/chat/completions，
    一套代码覆盖：局域网 Ollama、vLLM、DeepSeek、Moonshot、通义千问、SiliconFlow、OpenAI。
    LLM_BASE_URL 留空时自动回落到 OLLAMA_BASE_URL。
    """
    provider = (settings.llm_provider or "ollama").strip().lower()
    base_url = (settings.llm_base_url or "").strip() or settings.ollama_base_url

    if provider == "openai_compat":
        return OpenAICompatLLM(
            base_url=base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
        )
    if provider in ("ollama", ""):
        return OllamaLLM(
            base_url=settings.ollama_base_url,
            model=settings.llm_model,
            timeout=settings.llm_timeout,
        )
    raise ValueError(
        f"未知 LLM_PROVIDER={provider!r}，可选：ollama | openai_compat"
    )
