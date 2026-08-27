from app.core.config import settings
from app.guardrails.no_answer import should_no_answer


def test_no_answer_when_low_rerank():
    assert should_no_answer(top_score=0.1, threshold=0.3) is True
    assert should_no_answer(top_score=0.8, threshold=0.3) is False


def test_no_answer_at_exact_threshold():
    # 分数恰好等于阈值 → 不属于 no-answer（>= threshold 应回答）
    assert should_no_answer(top_score=0.3, threshold=0.3) is False


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.1] * 1024


class FakeReranker:
    def __init__(self, result):
        self._result = result

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        return self._result


def _patch_providers(monkeypatch, rerank_result):
    # build_query_graph 在函数体内 `from app.generation.providers import get_embedding, get_reranker`，
    # 因此必须 patch providers 模块属性（函数执行时才解析，patch 必然生效）。
    monkeypatch.setattr("app.generation.providers.get_embedding", lambda: FakeEmbedder())
    monkeypatch.setattr("app.generation.providers.get_reranker", lambda: FakeReranker(rerank_result))


def _patch_search(monkeypatch, retrieved):
    def fake_search(self, query_vec, top_k=5, roles=None, workspace_id=None):
        return retrieved

    monkeypatch.setattr("app.retrieval.vector_store.VectorStore.search", fake_search)


def test_graph_end_to_end_high_score(monkeypatch):
    from app.generation.graphs.query_graph import build_query_graph

    retrieved = [{
        "id": "chunk-1", "content": "销售目标超额完成，按年度绩效发放奖金。", "page_number": 3,
        "section_title": "薪酬", "distance": 0.1,
    }]
    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)])
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "奖金是多少", "roles": ["employee"]})

    assert result["no_answer"] is False
    assert "根据资料" in result["answer"]
    assert "奖金" in result["answer"]
    assert result["citations"] == [{"chunk_id": "chunk-1", "page": 3}]


def test_graph_no_answer_empty_retrieval(monkeypatch):
    from app.generation.graphs.query_graph import build_query_graph

    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)])
    _patch_search(monkeypatch, [])

    graph = build_query_graph()
    result = graph.invoke({"query": "不存在的问题", "roles": ["employee"]})

    assert result["no_answer"] is True
    assert result["answer"] == settings.no_answer_message
    assert result["citations"] == []


def test_graph_no_answer_low_rerank_score(monkeypatch):
    from app.generation.graphs.query_graph import build_query_graph

    retrieved = [{
        "id": "chunk-1", "content": "无关文档内容，用于验证低分护栏。", "page_number": 1,
        "section_title": "其他", "distance": 0.9,
    }]
    _patch_providers(monkeypatch, rerank_result=[(0, 0.1)])
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "不存在的问题", "roles": ["employee"]})

    assert result["no_answer"] is True
    assert result["answer"] == settings.no_answer_message
