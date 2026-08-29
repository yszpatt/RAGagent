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


# ---------------------------------------------------------------------------
# P0-1 两级 No-Answer 判定（docs/plans/2026-08-29-optimization-plan.md 实验 A）
#
# 背景：reranker 绝对分数域内外分布重叠，旧逻辑用 threshold=0.3 做门控，
# 实测误杀 40% 正确答案（口语化提问重灾区）。现改为：
#   Tier1 = embedding 余弦门控（宽松）/ Tier2 = reranker 仅排序 / Tier3 = LLM 终审
# ---------------------------------------------------------------------------

def test_tier1_gate_saves_high_cosine_low_rerank(monkeypatch):
    """核心回归：余弦相似度高但 reranker 分低时**必须回答**。

    这是本次修复的关键场景 —— 口语化提问（如「签了字能反悔吗」）的特征正是
    「向量看得懂、reranker 打分低」。旧逻辑用 rerank 0.3 门控会把它误杀。
    """
    from app.generation.graphs.query_graph import build_query_graph

    retrieved = [{
        "id": "chunk-1", "content": "违约金为人民币壹拾万元整。", "page_number": 8,
        "section_title": "违约责任", "distance": 0.3,   # → 余弦相似度 0.7，高于门控 0.55
    }]
    llm = FakeLLM(answer="违约金为壹拾万元整[1]。")
    # reranker 只给 0.05 分（远低于旧阈值 0.3），但它仍把该块排在第一位
    _patch_providers(monkeypatch, rerank_result=[(0, 0.05)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "签了字能反悔吗，要付什么代价", "roles": ["employee"]})

    assert result["no_answer"] is False, "高余弦命中被误杀 —— P0-1 回归"
    assert result["answer"] == "违约金为壹拾万元整[1]。"
    assert llm.context is not None, "Tier1 通过后必须真正调用 LLM"
    assert result["citations"] == [{"chunk_id": "chunk-1", "page": 8}]


def test_tier1_gate_rejects_low_cosine(monkeypatch):
    """Tier1：余弦相似度低于门控 → 直接拒答，且不消耗 LLM 调用。"""
    from app.generation.graphs.query_graph import build_query_graph

    retrieved = [{
        "id": "chunk-1", "content": "完全无关的文档内容。", "page_number": 1,
        "section_title": "其他", "distance": 0.8,   # → 余弦 0.2，低于门控 0.55
    }]
    llm = FakeLLM(answer="这段回答本不该出现。")
    # 即便 reranker 给高分，Tier1 也应先拦下
    _patch_providers(monkeypatch, rerank_result=[(0, 0.95)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "今天天气怎么样", "roles": ["employee"]})

    assert result["no_answer"] is True
    assert result["answer"] == settings.no_answer_message
    assert llm.context is None, "Tier1 拒答时不应浪费 LLM 调用"
    assert result["citations"] == []


def test_tier3_llm_final_check_no_answer(monkeypatch):
    """Tier3：余弦过关但 LLM 判定上下文中无答案 → 拒答。"""
    from app.generation.graphs.query_graph import build_query_graph
    from app.generation.providers.llm import NO_ANSWER_MARKER

    retrieved = [{
        "id": "chunk-1", "content": "差旅费报销标准说明。", "page_number": 5,
        "section_title": "财务", "distance": 0.2,   # → 余弦 0.8，通过门控
    }]
    llm = FakeLLM(answer=NO_ANSWER_MARKER)
    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "公司年会什么时候办", "roles": ["employee"]})

    assert result["no_answer"] is True, "LLM 终审判无答案时应拒答"
    assert result["answer"] == settings.no_answer_message
    assert result["citations"] == []


def test_llm_final_check_can_be_disabled(monkeypatch):
    """Tier3 可关闭：关闭后即便 LLM 输出拒答标记也照常返回原文。"""
    from app.generation.graphs.query_graph import build_query_graph
    from app.generation.providers.llm import NO_ANSWER_MARKER

    monkeypatch.setattr(settings, "llm_final_check", False)
    retrieved = [{
        "id": "chunk-1", "content": "差旅费报销标准说明。", "page_number": 5,
        "section_title": "财务", "distance": 0.2,
    }]
    llm = FakeLLM(answer=NO_ANSWER_MARKER)
    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "公司年会什么时候办", "roles": ["employee"]})

    assert result["no_answer"] is False
    assert result["answer"] == NO_ANSWER_MARKER


def test_backward_compat_rerank_threshold(monkeypatch):
    """向后兼容：answer_gate_enabled=False 时退回旧的 rerank 单阈值行为。"""
    from app.generation.graphs.query_graph import build_query_graph

    monkeypatch.setattr(settings, "answer_gate_enabled", False)
    retrieved = [{
        "id": "chunk-1", "content": "某段内容。", "page_number": 1,
        "section_title": "其他", "distance": 0.1,   # 余弦 0.9，新门控本应放行
    }]
    llm = FakeLLM(answer="正式回答。")
    # rerank 0.1 < 旧阈值 0.3 → 旧逻辑应拒答
    _patch_providers(monkeypatch, rerank_result=[(0, 0.1)], llm=llm)
    _patch_search(monkeypatch, retrieved)

    graph = build_query_graph()
    result = graph.invoke({"query": "问题", "roles": ["employee"]})

    assert result["no_answer"] is True, "兼容模式下应沿用 rerank_threshold 判定"
    assert llm.context is None


def test_similarity_derived_from_distance(monkeypatch):
    """retrieve 节点应把 pgvector 余弦距离换算成相似度（1 - distance）。"""
    from app.generation.graphs.query_graph import build_query_graph

    captured = {}

    def fake_search(self, query_vec, top_k=5, roles=None, workspace_id=None):
        captured["raw"] = [{
            "id": "c1", "content": "内容", "page_number": 1,
            "section_title": "节", "distance": 0.25,
        }]
        return captured["raw"]

    _patch_providers(monkeypatch, rerank_result=[(0, 0.9)])
    monkeypatch.setattr("app.retrieval.vector_store.VectorStore.search", fake_search)

    graph = build_query_graph()
    graph.invoke({"query": "问题", "roles": ["employee"]})

    assert abs(captured["raw"][0]["similarity"] - 0.75) < 1e-6
