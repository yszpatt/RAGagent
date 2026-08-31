import uuid
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.generation.graphs.query_graph import get_query_graph
from app.generation.providers.embedding import EmbeddingConfig, set_embedding_config
from app.retrieval.vector_store import VectorStore

router = APIRouter(prefix="/chat", tags=["chat"])

# 前端设置页下发的 embedding 配置经由此请求头透传（仅 chat 查询链路需要，
# 入库链路在 documents 路由另作处理）。
EMBEDDING_CFG_HEADER = "x-kp-embedding-cfg"


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, description="用户问题")
    conversation_id: uuid.UUID | None = Field(
        default=None, description="会话 ID；缺省则创建新会话"
    )


def _enrich_citations(citations: list) -> list:
    """给 citations 合并原文摘录/文档标题/节标题（供前端来源案卷展示）。

    引用 id 全部来自本次检索结果（已过角色过滤），此处仅做详情回填；
    DB 异常或缺记录时原样透传，不阻断问答。
    """
    if not citations:
        return []
    try:
        details = VectorStore().fetch_chunk_details(
            [c.get("chunk_id") for c in citations if isinstance(c, dict)]
        )
    except Exception:
        return citations
    out = []
    for c in citations:
        if isinstance(c, dict):
            d = details.get(str(c.get("chunk_id")))
            out.append({**c, **d} if d else c)
        else:
            out.append(c)
    return out


def _persist_exchange(payload: ChatRequest, answer: str, no_answer: bool,
                      citations: list) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID] | None:
    """问答双消息落库。失败仅打日志返回 None，不影响返回答案。"""
    try:
        # 局部导入避免测试 stub 图时强依赖 DB
        from app.api.v1.conversations import append_message, create_conversation
        from app.db import SessionLocal
        from sqlalchemy import text as sql_text

        conv_id = payload.conversation_id
        if conv_id is not None:
            with SessionLocal() as s:
                exists = s.execute(sql_text(
                    "SELECT 1 FROM conversations WHERE id = :id"
                ), {"id": conv_id}).fetchone()
            if not exists:
                return None
        else:
            conv_id = create_conversation(payload.query[:50])

        user_msg = append_message(conv_id, "user", payload.query)
        assistant_msg = append_message(conv_id, "assistant", answer,
                                       citations=citations, no_answer=no_answer)
        return assistant_msg, conv_id, user_msg
    except Exception:
        return None


@router.post("")
async def chat(payload: ChatRequest, request: Request):
    # 按请求下发的 embedding 配置（本地 / Ollama）设置本次查询上下文；
    # 图的 embed_query 调用时由分发器读取。未下发则回落到本地 bge-m3。
    set_embedding_config(
        EmbeddingConfig.from_header(request.headers.get(EMBEDDING_CFG_HEADER))
    )
    state = {"query": payload.query, "roles": ["admin", "manager", "employee"]}
    result = await run_in_threadpool(get_query_graph().invoke, state)
    citations = _enrich_citations(result["citations"])
    conversation_id = payload.conversation_id
    message_id = None
    persisted = _persist_exchange(payload, result["answer"],
                                  result["no_answer"], citations)
    if persisted:
        message_id, conversation_id, _ = persisted
    _write_query_audit(payload.query, citations, message_id)
    return {
        "answer": result["answer"],
        "no_answer": result["no_answer"],
        "citations": citations,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "message_id": str(message_id) if message_id else None,
    }


def _write_query_audit(query: str, citations: list, message_id: uuid.UUID | None):
    """查询审计：记录问题 + 命中的 chunk + 关联回答消息。失败不影响返回。"""
    try:
        from app.services.audit import write_audit

        chunk_ids = []
        for c in citations:
            try:
                chunk_ids.append(uuid.UUID(str(c.get("chunk_id"))))
            except (ValueError, TypeError, AttributeError):
                continue
        write_audit("query", query_text=query,
                    retrieved_chunk_ids=chunk_ids, response_ref=message_id)
    except Exception:
        pass
