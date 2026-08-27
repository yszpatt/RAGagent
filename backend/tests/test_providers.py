import asyncio

import httpx
import numpy as np

from app.generation.providers.base import EmbeddingProvider, LLMProvider, RerankerProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker
from app.generation.providers.llm import OllamaLLM


class FakeEmbeddingModel:
    """代替真实 SentenceTransformer，避免离线/CI 加载模型。"""

    def get_sentence_embedding_dimension(self) -> int:
        return 1024

    def encode(self, texts, normalize_embeddings=False):
        return np.zeros((len(texts), 1024))


def test_embedding_provider_interface():
    emb = BgeM3Embedding.__new__(BgeM3Embedding)  # 不加载真实模型
    emb._model = FakeEmbeddingModel()
    emb.dim = emb._model.get_sentence_embedding_dimension()
    assert isinstance(emb, EmbeddingProvider)
    assert emb.dim == 1024


def test_embedding_shape_contract():
    emb = BgeM3Embedding.__new__(BgeM3Embedding)
    emb._model = FakeEmbeddingModel()
    emb.dim = emb._model.get_sentence_embedding_dimension()
    q = emb.embed_query("测试")
    docs = emb.embed_documents(["a", "b"])
    assert len(q) == 1024
    assert len(docs) == 2
    assert all(len(d) == 1024 for d in docs)


def test_provider_factory_returns_correct_types():
    from app.generation.providers import get_llm

    # get_llm 无重依赖，可真实调用；embedding/reranker 工厂会加载模型，
    # 这里只验证类已正确接入 ABC，避免离线环境失败。
    assert isinstance(get_llm(), LLMProvider)
    assert issubclass(BgeM3Embedding, EmbeddingProvider)
    assert issubclass(BgeReranker, RerankerProvider)


def test_ollama_llm_sends_prompt_with_context(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": "答案"}

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **kw):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    llm = OllamaLLM()

    async def run():
        return await OllamaLLM.generate(llm, "违约金是多少", "合同第3页：违约金为10%")

    ans = asyncio.run(run())
    assert ans == "答案"
    assert "合同第3页：违约金为10%" in captured["json"]["prompt"]
    assert "违约金是多少" in captured["json"]["prompt"]
    assert "/api/generate" in captured["url"]
