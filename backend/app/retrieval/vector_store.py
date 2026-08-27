import uuid
from sqlalchemy import text
from pgvector import Vector

from app.db import SessionLocal


class VectorStore:
    def add_chunk(self, document_id, content, chunk_index, page_number, embedding, roles=None):
        # 入库时默认角色为全角色（开放读取），与 search 的失败关闭（fail-closed）形成对称：
        # 入库默认开放、检索无角色则返回空，权限收紧在读取侧。
        roles = roles or ["admin", "manager", "employee"]
        with SessionLocal() as s:
            chunk_id = uuid.uuid4()
            s.execute(text("""
                INSERT INTO chunks (id, document_id, content, chunk_index, page_number, token_count, embedding)
                VALUES (:id, :doc, :content, :idx, :page, :tc, :emb)
            """), {"id": chunk_id, "doc": document_id, "content": content,
                   "idx": chunk_index, "page": page_number, "tc": len(content),
                   "emb": embedding})
            for r in roles:
                s.execute(text("""
                    INSERT INTO document_permissions (id, document_id, role) VALUES (:pid, :doc, :role)
                    ON CONFLICT (document_id, role) DO NOTHING
                """), {"pid": uuid.uuid4(), "doc": document_id, "role": r})
            s.commit()

    def search(self, query_vec: list[float], top_k: int = 5, roles: list[str] | None = None,
               workspace_id=None):
        # 未指定 roles（None，历史调用方）沿用默认开放角色，保持既有接口行为；
        # 显式传入空列表（如用户上下文判定无任何角色）→ 失败关闭，防止越权读到全部文档。
        if roles is None:
            roles = ["admin", "manager", "employee"]
        if not roles:
            return []  # 无角色 → 无结果（失败关闭，防越权）
        workspace_id = str(workspace_id) if workspace_id else None
        with SessionLocal() as s:
            rows = s.execute(text("""
                SELECT c.id, c.content, c.page_number, c.section_title,
                       c.embedding <=> :q AS distance
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE EXISTS (
                    SELECT 1 FROM document_permissions dp
                    WHERE dp.document_id = c.document_id AND dp.role IN :roles
                )
                AND (:ws IS NULL OR d.workspace_id = :ws)
                ORDER BY distance ASC
                LIMIT :k
            """), {"q": Vector(query_vec), "roles": tuple(roles), "ws": workspace_id, "k": top_k}).fetchall()
            return [{"id": r[0], "content": r[1], "page_number": r[2],
                     "section_title": r[3], "distance": r[4]} for r in rows]
