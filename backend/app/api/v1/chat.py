from fastapi import APIRouter
from app.generation.graphs.query_graph import get_query_graph

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("")
async def chat(payload: dict):
    state = {"query": payload["query"], "roles": ["admin", "manager", "employee"]}
    result = get_query_graph().invoke(state)
    return {"answer": result["answer"], "no_answer": result["no_answer"], "citations": result["citations"]}
