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
        if not state.get("query") or not state.get("roles"):
            raise ValueError("QueryState 必须包含非空 query 与 roles")
        vec = embedder.embed_query(state["query"])
        state["retrieved"] = store.search(vec, top_k=10, roles=state["roles"])
        return state

    def rerank(state: QueryState) -> QueryState:
        if not state["retrieved"]:
            state["reranked"] = []
            return state
        docs = [r["content"] for r in state["retrieved"]]
        ranked = reranker.rerank(state["query"], docs)
        # reranker 返回 (原文索引, score) 对；把 score 与 chunk 绑定保存，
        # 供 generate 用真实分数做 no-answer 护栏判定。
        state["reranked"] = [
            {"chunk": state["retrieved"][i], "score": score}
            for i, score in ranked[:5]
        ]
        return state

    def generate(state: QueryState) -> QueryState:
        from app.generation.providers import get_llm

        top = state["reranked"][0] if state["reranked"] else None
        if top is None or should_no_answer(top["score"], threshold=settings.rerank_threshold):
            state["no_answer"] = True
            state["answer"] = settings.no_answer_message
            state["citations"] = []
        else:
            state["no_answer"] = False
            # 组装上下文（top 5 块）供 LLM 回答，带页码引用
            context = "\n\n".join(
                f"[{i+1}] (第{r['chunk'].get('page_number') or '?'}页) {r['chunk']['content']}"
                for i, r in enumerate(state["reranked"][:5])
            )
            llm = get_llm()
            try:
                # 图节点为同步，invoke 在 API 层经 run_in_threadpool 执行（该线程无事件循环），
                # 故 asyncio.run 安全；单测直接同步 invoke 同样安全。
                answer = asyncio.run(llm.generate(state["query"], context))
            except Exception:
                # Ollama 未运行等异常 → 降级为 top chunk 回显，保证 demo 永不 500。
                answer = f"根据资料：{top['chunk']['content'][:200]}"
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
