from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class RerankerProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        """返回 (原文索引, 分数) 按分数降序"""
        ...


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, context: str) -> str: ...
