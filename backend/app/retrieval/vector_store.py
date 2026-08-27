import uuid
from sqlalchemy import event, text
from pgvector import Vector
from pgvector.psycopg2 import register_vector

from app.db import SessionLocal, engine


# pgvector 的 psycopg2 适配器需在每个新连接上注册，否则 list 参数
# 会被绑定为 numeric[]，导致 `vector <=> numeric[]` 无匹配运算符。
event.listen(engine, "connect", lambda dbapi_conn, _rec: register_vector(dbapi_conn))


class VectorStore:
    def add_chunk(self, document_id, content, chunk_index, page_number, embedding, roles=None):
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

    def search(self, query_vec, top_k=5, roles=None, workspace_id=None):
        roles = roles or ["admin", "manager", "employee"]
        with SessionLocal() as s:
            rows = s.execute(text("""
                SELECT DISTINCT c.id, c.content, c.page_number, c.section_title,
                       c.embedding <=> :q AS distance
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                JOIN document_permissions dp ON d.id = dp.document_id
                WHERE dp.role IN :roles
                  AND (:ws IS NULL OR d.workspace_id = :ws)
                ORDER BY distance ASC
                LIMIT :k
            """), {"q": Vector(query_vec), "roles": tuple(roles), "ws": workspace_id, "k": top_k}).fetchall()
            return [{"id": r[0], "content": r[1], "page_number": r[2],
                     "section_title": r[3], "distance": r[4]} for r in rows]
