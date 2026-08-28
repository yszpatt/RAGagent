import uuid
from sqlalchemy import text
from pgvector import Vector

from app.db import SessionLocal


class VectorStore:
    def add_chunks(self, document_id, chunks, roles=None):
        """批量入库：一个文档的所有 chunk + 权限，单事务。

        chunks: list of dicts
            {content, chunk_index, page_number, section_title, embedding}
        任一条失败整体回滚，杜绝"部分 chunk 已入库、其余失败"的孤儿数据。
        """
        # 入库时默认角色为全角色（开放读取），与 search 的失败关闭（fail-closed）形成对称：
        # 入库默认开放、检索无角色则返回空，权限收紧在读取侧。
        roles = roles or ["admin", "manager", "employee"]
        with SessionLocal() as s:
            for c in chunks:
                s.execute(text("""
                    INSERT INTO chunks (id, document_id, content, chunk_index, page_number, section_title, token_count, embedding)
                    VALUES (:id, :doc, :content, :idx, :page, :section, :tc, :emb)
                """), {"id": str(uuid.uuid4()), "doc": document_id, "content": c["content"],
                       "idx": c["chunk_index"], "page": c.get("page_number"), "section": c.get("section_title"),
                       "tc": len(c["content"]), "emb": c["embedding"]})
            for r in roles:
                s.execute(text("""
                    INSERT INTO document_permissions (id, document_id, role) VALUES (:id, :doc, :role)
                    ON CONFLICT (document_id, role) DO NOTHING
                """), {"id": str(uuid.uuid4()), "doc": document_id, "role": r})
            s.commit()

    def add_chunk(self, document_id, content, chunk_index, page_number, embedding, roles=None):
        """单条入库（向后兼容），委托给 add_chunks。"""
        self.add_chunks(document_id, [{
            "content": content,
            "chunk_index": chunk_index,
            "page_number": page_number,
            "embedding": embedding,
        }], roles=roles)

    def fetch_chunk_details(self, chunk_ids) -> dict:
        """按 chunk id 批量取引用详情（原文摘录/页码/节标题/文档标题）。

        返回 {chunk_id_str: {excerpt, page, section, document_title}}；
        非法 id 与查不到的 id 不出现在结果中，调用方按需回退。
        """
        ids = []
        for cid in chunk_ids or []:
            try:
                ids.append(uuid.UUID(str(cid)))
            except (ValueError, TypeError):
                continue
        if not ids:
            return {}
        with SessionLocal() as s:
            rows = s.execute(text("""
                SELECT c.id, c.content, c.page_number, c.section_title, d.title
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE c.id IN :ids
            """), {"ids": tuple(ids)}).fetchall()
        details = {}
        for r in rows:
            content = r[1] or ""
            details[str(r[0])] = {
                "excerpt": content[:200] + ("…" if len(content) > 200 else ""),
                "page": r[2],
                "section": r[3],
                "document_title": r[4],
            }
        return details

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
