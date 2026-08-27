from sentence_transformers import CrossEncoder
from app.generation.providers.base import RerankerProvider


class BgeReranker(RerankerProvider):
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        pairs = [(query, d) for d in docs]
        scores = self._model.predict(pairs)
        ranked = sorted(((i, float(s)) for i, s in enumerate(scores)), key=lambda x: -x[1])
        return ranked
