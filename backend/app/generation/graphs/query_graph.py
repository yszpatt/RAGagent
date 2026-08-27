from typing import TypedDict

from langgraph.graph import StateGraph, END


class QueryState(TypedDict):
    query: str
    roles: list[str]
    retrieved: list
    reranked: list
    answer: str
    no_answer: bool
    citations: list


def build_query_graph():
    from app.core.config import settings
    from app.retrieval.vector_store import VectorStore
    from app.generation.providers import get_embedding, get_reranker
    from app.guardrails.no_answer import should_no_answer

    store = VectorStore()
    embedder = get_embedding()
    reranker = get_reranker()

    def retrieve(state: QueryState) -> QueryState:
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
        top = state["reranked"][0] if state["reranked"] else None
        if top is None or should_no_answer(top["score"], threshold=settings.rerank_threshold):
            state["no_answer"] = True
            state["answer"] = settings.no_answer_message
            state["citations"] = []
        else:
            state["no_answer"] = False
            state["answer"] = f"根据资料：{top['chunk']['content'][:200]}"
            state["citations"] = [
                {"chunk_id": str(top["chunk"]["id"]), "page": top["chunk"]["page_number"]}
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
    # TODO(Task 8+): 接入 get_llm() 把 top chunk 作为 context 生成正式回答。
    # 本 Task 按实现计划保持最小版本：直接拼接 top chunk 内容前缀。
    return g.compile()
