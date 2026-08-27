from fastapi import APIRouter

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations():
    # demo: 会话持久化后续接入；当前返回空列表
    return {"data": [], "meta": {"total": 0}}
