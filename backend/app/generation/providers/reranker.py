import numpy as np
from sentence_transformers import CrossEncoder

from app.generation.providers.base import RerankerProvider
from app.generation.providers.embedding import OllamaEmbedding


class BgeReranker(RerankerProvider):
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        pairs = [(query, d) for d in docs]
        scores = self._model.predict(pairs)
        ranked = sorted(((i, float(s)) for i, s in enumerate(scores)), key=lambda x: -x[1])
        return ranked


class OllamaBiEncoderReranker(RerankerProvider):
    """LAN 双塔（bi-encoder）重排：复用 Ollama bge-m3 的 /api/embed 做相似度排序。

    动机：把 reranker 也迁到局域网 Ollama，去掉本机 sentence-transformers（2.2G）+ torch。
    当前 qllama 分支未实现 /api/rerank，cross-encoder（bge-reranker-v2-m3）无法经 API 调用；
    双塔重排复用已验证可用的 /api/embed，是当下能落地的 LAN 方案。

    质量权衡：弱于 cross-encoder。但本系统 reranker 仅用于 Tier2 排序
    （Tier1 门控=embedding 余弦，Tier3 终审=LLM），不参与判定，影响有限。
    待 Ollama 侧具备 /api/rerank 后，可切回 cross-encoder 提供方。
    """

    def __init__(self, base_url: str, model: str = "bge-m3", timeout: float = 60.0):
        self._embed = OllamaEmbedding(base_url=base_url, model=model, timeout=timeout)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        if not docs:
            return []
        q = np.asarray(self._embed.embed_query(query), dtype=np.float32)
        d_vecs = [np.asarray(v, dtype=np.float32) for v in self._embed.embed_documents(docs)]
        # OllamaEmbedding 已做 L2 归一化，点积即余弦相似度。
        sims = [float(np.dot(q, d)) for d in d_vecs]
        return sorted(((i, s) for i, s in enumerate(sims)), key=lambda x: -x[1])

