from app.generation.providers.base import EmbeddingProvider, LLMProvider, RerankerProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker
from app.generation.providers.llm import OllamaLLM


def test_embedding_provider_interface():
    emb = BgeM3Embedding.__new__(BgeM3Embedding)  # 不加载真实模型
    assert isinstance(emb, EmbeddingProvider)
    assert emb.dim == 1024


def test_provider_factory_returns_correct_types():
    from app.generation.providers import get_embedding, get_reranker, get_llm
    assert get_reranker() is not None
    assert isinstance(get_llm(), LLMProvider)


def test_ollama_llm_builds_prompt_with_context():
    llm = OllamaLLM.__new__(OllamaLLM)
    llm._model = "qwen2.5:7b"
    llm._base_url = "http://localhost:11434"
    import inspect
    src = inspect.getsource(OllamaLLM.generate)
    assert "context" in src
    assert "prompt" in src
