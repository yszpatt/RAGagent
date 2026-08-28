import json
import uuid
from fastapi import APIRouter, HTTPException
from sqlalchemy import text as sql_text

from app.db import SessionLocal
from app.services.context import default_user_id, default_workspace_id

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations():
    """列出当前用户的会话（按最近消息时间倒序），供前端会话侧栏。"""
    user_id = default_user_id()
    with SessionLocal() as s:
        rows = s.execute(sql_text("""
            SELECT c.id, c.title, c.created_at,
                   MAX(m.created_at) AS last_at,
                   COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id = :user
            GROUP BY c.id
            ORDER BY COALESCE(MAX(m.created_at), c.created_at) DESC
        """), {"user": user_id}).fetchall()
    return {
        "data": [
            {
                "id": str(r[0]),
                "title": r[1],
                "created_at": str(r[2]),
                "last_message_at": str(r[3]) if r[3] else None,
                "message_count": int(r[4]),
            }
            for r in rows
        ],
        "meta": {"total": len(rows)},
    }


@router.get("/{conversation_id}/messages")
async def get_messages(conversation_id: str):
    """会话消息历史（user/assistant 顺序返回，citations 为富化后的 JSONB）。"""
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的会话 ID")
    with SessionLocal() as s:
        row = s.execute(sql_text(
            "SELECT id FROM conversations WHERE id = :id"
        ), {"id": conv_uuid}).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        rows = s.execute(sql_text("""
            SELECT id, role, content, citations, no_answer, created_at
            FROM messages
            WHERE conversation_id = :conv
            ORDER BY created_at ASC
        """), {"conv": conv_uuid}).fetchall()
    return {
        "data": [
            {
                "id": str(r[0]),
                "role": r[1],
                "content": r[2],
                "citations": r[3],
                "no_answer": r[4],
                "created_at": str(r[5]),
            }
            for r in rows
        ],
        "meta": {"total": len(rows)},
    }


def create_conversation(title: str) -> uuid.UUID:
    """供 chat 端点复用：创建会话并返回 id。"""
    conv_id = uuid.uuid4()
    with SessionLocal() as s:
        s.execute(sql_text(
            "INSERT INTO conversations (id, user_id, workspace_id, title) "
            "VALUES (:id, :user, :ws, :title)"
        ), {"id": conv_id, "user": default_user_id(),
            "ws": default_workspace_id(), "title": title})
        s.commit()
    return conv_id


def append_message(conversation_id: uuid.UUID, role: str, content: str,
                   citations: list | None = None, no_answer: bool = False) -> uuid.UUID:
    """供 chat 端点复用：写入一条消息，返回消息 id。"""
    msg_id = uuid.uuid4()
    with SessionLocal() as s:
        s.execute(sql_text(
            "INSERT INTO messages (id, conversation_id, role, content, citations, no_answer) "
            "VALUES (:id, :conv, :role, :content, CAST(:citations AS jsonb), :no_answer)"
        ), {"id": msg_id, "conv": conversation_id, "role": role, "content": content,
            "citations": json.dumps(citations or []),
            "no_answer": no_answer})
        s.commit()
    return msg_id
