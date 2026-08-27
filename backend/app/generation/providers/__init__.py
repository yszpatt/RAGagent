from functools import lru_cache
from app.generation.providers.base import EmbeddingProvider, RerankerProvider, LLMProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker
from app.generation.providers.llm import OllamaLLM
from app.core.config import settings


@lru_cache
def get_embedding() -> EmbeddingProvider:
    return BgeM3Embedding(settings.embedding_model)


@lru_cache
def get_reranker() -> RerankerProvider:
    return BgeReranker(settings.reranker_model)


@lru_cache
def get_llm() -> LLMProvider:
    return OllamaLLM(settings.ollama_base_url, settings.llm_model)
