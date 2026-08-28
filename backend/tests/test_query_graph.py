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


class FakeLLM:
    """记录 prompt/context，可按需抛异常模拟 Ollama 不可用。"""

    def __init__(self, answer="这是由 LLM 生成的正式回答。", raise_on_call=False):
        self._answer = answer
        self._raise_on_call = raise_on_call
        self.prompt = None
        self.context = None

    async def generate(self, prompt: str, context: str) -> str:
        self.prompt = prompt
        self.context = context
        if self._raise_on_call:
            raise RuntimeError("Ollama 不可用")
        return self._answer


def _patch_providers(monkeypatch, rerank_result, llm=None):
    # build_query_graph 在函数体内 `from app.generation.providers import get_embedding, get_reranker`，
    # generate 节点内 `from app.generation.providers import get_llm`，
    # 因此必须 patch providers 模块属性（函数执行时才解析，patch 必然生效）。
    monkeypatch.setattr("app.generation.providers.get_embedding", lambda: FakeEmbedder())
    monkeypatch.setattr("app.generation.providers.get_reranker", lambda: FakeReranker(rerank_result))
    monkeypatch.setattr("app.generation.providers.get_llm", lambda: llm or FakeLLM())


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
    llm = FakeLLM(answer="奖金按年度绩效发放，且须销售目标超额完成。")
    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "奖金是多少", "roles": ["employee"]})

    assert result["no_answer"] is False
    assert result["answer"] == "奖金按年度绩效发放，且须销售目标超额完成。"
    assert llm.context is not None and "销售目标超额完成" in llm.context  # LLM 拿到 top chunk 上下文
    assert llm.context is not None and "第3页" in llm.context  # 上下文带页码引用
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


def test_graph_multi_doc_rerank_index_mapping(monkeypatch):
    """rerank 返回 (1, 0.9) 时，答案与引用应来自 retrieved[1]"""
    from app.generation.graphs.query_graph import build_query_graph

    retrieved = [
        {"id": "chunk-0", "content": "低相关内容。", "page_number": 1, "section_title": "其他", "distance": 0.9},
        {"id": "chunk-1", "content": "正确答案内容。", "page_number": 2, "section_title": "薪酬", "distance": 0.2},
    ]
    llm = FakeLLM(answer="正式回答。")
    _patch_providers(monkeypatch, rerank_result=[(1, 0.9)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "答案是什么", "roles": ["employee"]})

    assert result["no_answer"] is False
    assert result["answer"] == "正式回答。"
    # LLM 上下文应只含 retrieved[1]，不含 retrieved[0]；引用同样来自 chunk-1
    assert "正确答案内容" in llm.context
    assert "低相关内容" not in llm.context
    assert result["citations"] == [{"chunk_id": "chunk-1", "page": 2}]


def test_graph_llm_failure_falls_back_to_echo(monkeypatch):
    """LLM 调用失败（如 Ollama 未运行）时应降级为 top chunk 回显，不抛 500"""
    from app.generation.graphs.query_graph import build_query_graph

    retrieved = [{
        "id": "chunk-1", "content": "销售目标超额完成，按年度绩效发放奖金。", "page_number": 3,
        "section_title": "薪酬", "distance": 0.1,
    }]
    llm = FakeLLM(raise_on_call=True)
    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "奖金是多少", "roles": ["employee"]})

    assert result["no_answer"] is False
    assert "根据资料" in result["answer"]
    assert "奖金" in result["answer"]
    assert result["citations"] == [{"chunk_id": "chunk-1", "page": 3}]


def test_graph_roles_passthrough(monkeypatch):
    """roles 应原样透传给 VectorStore.search"""
    from app.generation.graphs.query_graph import build_query_graph

    captured = {}

    def fake_search(self, query_vec, top_k=5, roles=None, workspace_id=None):
        captured["roles"] = roles
        return []

    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)])
    monkeypatch.setattr("app.retrieval.vector_store.VectorStore.search", fake_search)

    graph = build_query_graph()
    graph.invoke({"query": "我的福利", "roles": ["employee"]})

    assert captured["roles"] == ["employee"]
