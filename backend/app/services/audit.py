"""审计埋点：query / upload / permission_change / delete 四类动作全量留痕。

设计文档 §8 要求关键动作可追溯；写失败只吞掉（审计是旁路，不阻断主流程）。
"""
import uuid

from sqlalchemy import text

from app.db import SessionLocal
from app.services.context import default_user_id, default_workspace_id


def write_audit(
    action: str,
    query_text: str | None = None,
    retrieved_chunk_ids: list[uuid.UUID] | None = None,
    response_ref: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    try:
        with SessionLocal() as s:
            s.execute(text(
                "INSERT INTO audit_logs "
                "(id, user_id, workspace_id, action, query_text, retrieved_chunk_ids, response_ref) "
                "VALUES (:id, :user, :ws, :action, :query_text, :chunks, :ref)"
            ), {
                "id": uuid.uuid4(),
                "user": user_id or default_user_id(),
                "ws": default_workspace_id(),
                "action": action,
                "query_text": query_text,
                "chunks": retrieved_chunk_ids or None,
                "ref": response_ref,
            })
            s.commit()
    except Exception:
        # 审计不可用不应影响问答/上传主流程
        pass
