from sentence_transformers import SentenceTransformer
from app.generation.providers.base import EmbeddingProvider


class BgeM3Embedding(EmbeddingProvider):
    dim = 1024

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()
