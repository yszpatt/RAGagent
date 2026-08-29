import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, END


class QueryState(TypedDict):
    """图调用的状态契约。

    调用方只需提供 query + roles，其余键（retrieved / reranked / answer /
    no_answer / citations）由管线各节点按序填充。
    """

    query: str
    roles: list[str]
    retrieved: list
    reranked: list
    answer: str
    no_answer: bool
    citations: list


_graph = None

# 进入 rerank 的候选数。去重后截到这个数量，reranker 只看多样候选。
_RETRIEVE_K = 10


def get_query_graph():
    """惰性单例：首次调用才构建图（此时才加载模型）。"""
    global _graph
    if _graph is None:
        _graph = build_query_graph()
    return _graph


def build_query_graph():
    from app.core.config import settings
    from app.retrieval.vector_store import VectorStore
    from app.generation.providers import get_embedding, get_reranker
    from app.guardrails.no_answer import should_no_answer

    store = VectorStore()
    embedder = get_embedding()
    reranker = get_reranker()

    def retrieve(state: QueryState) -> QueryState:
        from app.retrieval.dedup import dedup_hits

        if not state.get("query") or not state.get("roles"):
            raise ValueError("QueryState 必须包含非空 query 与 roles")
        vec = embedder.embed_query(state["query"])
        # 去重前多取一倍候选：若 top10 里有一半是重复，去重后就只剩 5 个有效候选。
        # ANN 检索 20 条与 10 条开销几乎相同，但能保证去重后仍有 10 个多样候选。
        fetch_k = _RETRIEVE_K * 2
        hits = store.search(vec, top_k=fetch_k, roles=state["roles"])
        if settings.dedup_enabled:
            hits = dedup_hits(hits, settings.dedup_threshold)[:_RETRIEVE_K]
        # pgvector 的 <=> 返回余弦「距离」，转成相似度供 Tier1 门控使用。
        # 实测（docs/plans/2026-08-29-optimization-plan.md 实验 A）：
        # 余弦相似度的域内外分布存在干净间隙，而 reranker 绝对分数重叠，
        # 故门控职责交给 embedding，reranker 只负责排序。
        for h in hits:
            d = h.get("distance")
            h["similarity"] = (1.0 - float(d)) if d is not None else None
        state["retrieved"] = hits
        return state

    def rerank(state: QueryState) -> QueryState:
        if not state["retrieved"]:
            state["reranked"] = []
            return state
        docs = [r["content"] for r in state["retrieved"]]
        ranked = reranker.rerank(state["query"], docs)
        # reranker 返回 (原文索引, score) 对。此处 score 仅用于排序与可观测性，
        # 不再参与 No-Answer 判定 —— 它的绝对量纲在域内外是重叠的。
        state["reranked"] = [
            {"chunk": state["retrieved"][i], "score": score}
            for i, score in ranked[:5]
        ]
        return state

    def _no_answer(state: QueryState) -> QueryState:
        state["no_answer"] = True
        state["answer"] = settings.no_answer_message
        state["citations"] = []
        return state

    def generate(state: QueryState) -> QueryState:
        """两级 No-Answer 判定（见 docs/plans/2026-08-29-optimization-plan.md）。

        Tier1 门控：检索到的最高余弦相似度 < answer_gate → 直接拒答，不消耗 LLM。
                   取 max 而非 reranker 的 top1，保证门控宽松 —— 实测误杀代价
                   （40% 正确答案被吞）远大于漏拒。
        Tier2 精排：reranker 只决定「用哪几段」，不参与是否回答的判定。
        Tier3 终审：LLM 读上下文判断能否回答，输出 __NO_ANSWER__ 则拒答。
                   基于内容判断而非分数分布，因此不受语料规模增长影响。
        """
        from app.generation.providers import get_llm
        from app.generation.providers.llm import extract_no_answer

        if not state["reranked"]:
            return _no_answer(state)

        # ---- Tier1：embedding 余弦门控 ----
        if settings.answer_gate_enabled:
            sims = [
                r["chunk"].get("similarity") for r in state["reranked"]
                if r["chunk"].get("similarity") is not None
            ]
            if sims and max(sims) < settings.answer_gate:
                return _no_answer(state)
        else:
            # 向后兼容：关掉新门控时退回旧的 rerank 单阈值行为
            top = state["reranked"][0]
            if should_no_answer(top["score"], threshold=settings.rerank_threshold):
                return _no_answer(state)

        # ---- Tier2：reranker 已排好序，组装上下文 ----
        context = "\n\n".join(
            f"[{i+1}] (第{r['chunk'].get('page_number') or '?'}页) {r['chunk']['content']}"
            for i, r in enumerate(state["reranked"][:5])
        )
        top_chunk = state["reranked"][0]["chunk"]

        llm = get_llm()
        llm_failed = False
        try:
            # 图节点为同步，invoke 在 API 层经 run_in_threadpool 执行（该线程无事件循环），
            # 故 asyncio.run 安全；单测直接同步 invoke 同样安全。
            answer = asyncio.run(llm.generate(state["query"], context))
        except Exception:
            # LLM 不可用（如 Ollama 未启动）→ 降级为检索片段回显，保证 demo 永不 500。
            llm_failed = True
            answer = f"根据资料：{top_chunk['content'][:200]}"

        # ---- Tier3：LLM 终审 ----
        if not llm_failed and settings.llm_final_check and extract_no_answer(answer):
            return _no_answer(state)

        state["no_answer"] = False
        state["answer"] = answer
        state["citations"] = [
            {"chunk_id": str(r["chunk"]["id"]), "page": r["chunk"].get("page_number")}
            for r in state["reranked"][:5]
        ]
        return state

    g = StateGraph(QueryState)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("generate", generate)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "generate")
    g.add_edge("generate", END)
    return g.compile()
