import asyncio

import httpx
import numpy as np

from app.generation.providers.base import EmbeddingProvider, LLMProvider, RerankerProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker
from app.generation.providers.llm import OllamaLLM, OpenAICompatLLM, SYSTEM_PROMPT


class FakeEmbeddingModel:
    """代替真实 SentenceTransformer，避免离线/CI 加载模型。"""

    def get_sentence_embedding_dimension(self) -> int:
        return 1024

    # 接收 **kwargs：真实 SentenceTransformer.encode 支持 batch_size /
    # show_progress_bar 等参数，桩需容忍这些调用，否则会掩盖真实接口契约。
    def encode(self, texts, normalize_embeddings=False, **kwargs):
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


def _fake_async_client(captured):
    """捕获 provider 实际发出的 payload 的 httpx.AsyncClient 替身。"""

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            # 同时满足两种协议：Ollama 原生读 ["response"]，
            # OpenAI 兼容读 ["choices"][0]["message"]["content"]。
            return {
                "response": "答案",
                "choices": [{"message": {"content": "答案"}}],
            }

    class FakeClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None, **kw):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    return FakeClient


def test_openai_compat_sends_temperature_zero(monkeypatch):
    """Tier3 判定必须可复现：不显式下发 temperature 时 Ollama 取默认 0.8，
    同一条查询重复 5 次会出现 1~2 次判定翻转（实测，见 plan §8）。
    """
    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured))
    llm = OpenAICompatLLM(base_url="http://host:11434", model="m")
    asyncio.run(llm.generate("问题", "资料[1]：内容"))

    assert captured["json"]["temperature"] == 0.0
    assert captured["url"].endswith("/chat/completions")


def test_ollama_native_sends_temperature_zero(monkeypatch):
    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured))
    llm = OllamaLLM()
    asyncio.run(llm.generate("问题", "资料[1]：内容"))

    # Ollama 原生接口把采样参数放在 options 里，不是顶层
    assert captured["json"]["options"]["temperature"] == 0.0


def test_temperature_is_configurable(monkeypatch):
    """默认 0，但允许显式覆盖（例如想让回答更有变化时）。"""
    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", _fake_async_client(captured))
    llm = OpenAICompatLLM(base_url="http://host:11434", model="m", temperature=0.7)
    asyncio.run(llm.generate("问题", "资料"))
    assert captured["json"]["temperature"] == 0.7


def test_system_prompt_covers_both_mismatch_classes():
    """SYSTEM_PROMPT 必须同时约束两类错配。

    只写甲类（术语映射）会漏放行：实测域内 +1 域外 -1，净零 —— 模型会拿
    本公司合同回答「一般公司的违约金是怎么算的」。两类规则缺一不可。
    """
    assert "术语错配" in SYSTEM_PROMPT and "作用域错配" in SYSTEM_PROMPT
    # 甲类：口语 → 书面语的映射示例
    assert "作废" in SYSTEM_PROMPT and "解除" in SYSTEM_PROMPT
    # 乙类：识别「问外部规定 / 普遍情况」的信号词
    for kw in ("一般", "劳动法", "民法典", "行业标准"):
        assert kw in SYSTEM_PROMPT, f"SYSTEM_PROMPT 缺少作用域越界信号词 {kw}"
    # 甲类允许一步推理，但禁止跨片段拼装编造
    assert "一步直接推理" in SYSTEM_PROMPT
    assert "禁止拼接多条资料" in SYSTEM_PROMPT
