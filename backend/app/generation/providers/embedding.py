import contextvars
from dataclasses import dataclass
from functools import lru_cache

import httpx
import numpy as np
from sentence_transformers import SentenceTransformer

from app.generation.providers.base import EmbeddingProvider

# 批量推理的批大小。实测（docs/plans/2026-08-29-optimization-plan.md 实验 D）：
# 120 块文本，逐块调用 40.08s → 批量(32) 25.55s，提速 1.6x（CPU）。
# GPU 环境下收益会显著更大。
DEFAULT_BATCH_SIZE = 32

# bge-m3 输出维度（本地与 Ollama 一致）。
BGE_M3_DIM = 1024

_EMBEDDING_CFG_VAR: contextvars.ContextVar = contextvars.ContextVar(
    "embedding_cfg", default=None
)


@dataclass
class EmbeddingConfig:
    """embedding 提供方配置，可由前端设置页下发（经由请求头透传）。

    provider:
      "local"  —— 本地 sentence-transformers 加载 bge-m3（默认，无需外部服务）
      "ollama" —— 走 Ollama 的 /api/embed 端点（模型须已在 Ollama 侧 pull，如 bge-m3）
    """

    provider: str = "local"
    ollama_url: str | None = None  # 形如 http://192.168.1.50:11434
    model: str = "bge-m3"

    @classmethod
    def from_header(cls, raw: str | None) -> "EmbeddingConfig | None":
        """解析请求头 X-KP-Embedding-Cfg（JSON）。非法或缺失返回 None。"""
        if not raw:
            return None
        try:
            data = __import__("json").loads(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        provider = str(data.get("provider", "local")).strip().lower()
        ollama_url = data.get("ollama_url") or None
        model = str(data.get("model") or "bge-m3").strip()
        if provider == "ollama":
            if not ollama_url:
                return None
            return cls(provider="ollama", ollama_url=str(ollama_url).strip(), model=model)
        return cls(provider="local", ollama_url=ollama_url, model=model)


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


class OllamaEmbedding(EmbeddingProvider):
    """走 Ollama /api/embed 的 embedding（默认 bge-m3）。

    与本地 sentence-transformers 保持一致：输出做 L2 归一化，
    使 pgvector 的余弦距离与既有（归一化）向量可比。
    ⚠️ 同一知识库内 embedding 提供方必须一致；切换后需重新 ingest 全部文档。
    """

    def __init__(self, base_url: str, model: str = "bge-m3", timeout: float = 120.0):
        self.base_url = str(base_url).rstrip("/")
        self.model = model
        self.timeout = timeout
        self.dim = BGE_M3_DIM

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        resp = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": inputs},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if "embeddings" in data:
            vectors = [np.asarray(v, dtype=np.float32) for v in data["embeddings"]]
        elif "embedding" in data:
            vectors = [np.asarray(data["embedding"], dtype=np.float32)]
        else:
            raise ValueError(f"Ollama /api/embed 返回缺少 embeddings 字段: {list(data.keys())}")
        # L2 归一化，与本地 bge-m3（normalize_embeddings=True）对齐。
        out = []
        for v in vectors:
            norm = np.linalg.norm(v)
            out.append((v / norm).tolist() if norm > 0 else v.tolist())
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


@lru_cache(maxsize=None)
def _local_embedding() -> BgeM3Embedding:
    return BgeM3Embedding("BAAI/bge-m3")


_ollama_cache: dict[str, OllamaEmbedding] = {}


def _ollama_embedding(url: str, model: str) -> OllamaEmbedding:
    key = f"{url}|{model}"
    cached = _ollama_cache.get(key)
    if cached is None:
        cached = OllamaEmbedding(url, model)
        _ollama_cache[key] = cached
    return cached


class DispatcherEmbedding(EmbeddingProvider):
    """按当前请求的 embedding 配置分发到本地或 Ollama 提供方。

    - 查询链路（chat）：由 chat 路由通过上下文变量按请求注入配置；
    - 入库链路（worker）：pipeline 直接显式传入配置，不经过此分发表。
    dim 固定为 bge-m3 维度（两种提供方均为 bge-m3）。
    """

    dim = BGE_M3_DIM

    def _resolve(self) -> EmbeddingProvider:
        cfg = _EMBEDDING_CFG_VAR.get()
        if cfg is not None and cfg.provider == "ollama" and cfg.ollama_url:
            return _ollama_embedding(cfg.ollama_url, cfg.model)
        return _local_embedding()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._resolve().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._resolve().embed_query(text)


def get_embedding_config() -> EmbeddingConfig | None:
    return _EMBEDDING_CFG_VAR.get()


def set_embedding_config(cfg: EmbeddingConfig | None) -> None:
    """设置本次请求（上下文）的 embedding 配置。chat 路由在调用图之前调用。"""
    _EMBEDDING_CFG_VAR.set(cfg)


def build_embedder(cfg: EmbeddingConfig | None) -> EmbeddingProvider:
    """按配置构造提供方，供入库链路（worker 无请求上下文）显式使用。"""
    if cfg is not None and cfg.provider == "ollama" and cfg.ollama_url:
        return _ollama_embedding(cfg.ollama_url, cfg.model)
    return _local_embedding()
