from sentence_transformers import SentenceTransformer
from app.generation.providers.base import EmbeddingProvider

# 批量推理的批大小。实测（docs/plans/2026-08-29-optimization-plan.md 实验 D）：
# 120 块文本，逐块调用 40.08s → 批量(32) 25.55s，提速 1.6x（CPU）。
# GPU 环境下收益会显著更大。
DEFAULT_BATCH_SIZE = 32


class BgeM3Embedding(EmbeddingProvider):
    """bge-m3 embedding（1024 维）。

    除批量推理外，本类还承担一个重要职责：**它是 No-Answer Tier1 门控的信号来源**。
    实测表明 bge-m3 的余弦相似度在「域内/域外」上存在干净的可分间隙，
    而 reranker 的绝对分数是重叠的 —— 因此门控用 embedding，排序用 reranker。
    详见 docs/plans/2026-08-29-optimization-plan.md 实验 A。
    """

    # 类级默认值：测试可能用 __new__ 绕过 __init__ 构造实例，
    # 此时实例属性尚未设置，需有兜底值保证 embed_documents 可用。
    _batch_size: int = DEFAULT_BATCH_SIZE

    def __init__(self, model_name: str = "BAAI/bge-m3", batch_size: int = DEFAULT_BATCH_SIZE):
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()
        self._batch_size = max(1, int(batch_size))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

    def embed_query(self, text: str) -> list[float]:
        # 单条查询不需要 batch_size / 进度条参数，保持最小签名以便测试桩替换。
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()
