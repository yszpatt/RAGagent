from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.generation.graphs.query_graph import get_query_graph

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, description="用户问题")


@router.post("")
async def chat(payload: ChatRequest):
    state = {"query": payload.query, "roles": ["admin", "manager", "employee"]}
    result = await run_in_threadpool(get_query_graph().invoke, state)
    return {"answer": result["answer"], "no_answer": result["no_answer"], "citations": result["citations"]}
