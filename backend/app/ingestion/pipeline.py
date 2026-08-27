import uuid
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.generation.providers import get_embedding
from app.ingestion.chunkers.recursive import recursive_chunk
from app.ingestion.parsers.registry import parse
from app.retrieval.vector_store import VectorStore

DEFAULT_WORKSPACE_NAME = "默认工作区"


def _resolve_workspace_id() -> uuid.UUID:
    """返回第一个 workspace；若不存在则创建一个默认 workspace。

    demo 阶段 pipeline 无用户上下文，用默认 workspace 兜底，
    保证 documents 行（FK -> workspaces.id）始终可写。
    """
    with SessionLocal() as s:
        row = s.execute(text(
            "SELECT id FROM workspaces ORDER BY created_at LIMIT 1"
        )).first()
        if row:
            return row[0]
        ws_id = uuid.uuid4()
        s.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, :name)"
        ), {"id": ws_id, "name": DEFAULT_WORKSPACE_NAME})
        s.commit()
        return ws_id


def _upsert_document(doc_id: uuid.UUID, workspace_id: uuid.UUID, path: str) -> None:
    """先落 documents 行，保证 add_chunk 插入 document_permissions 时 FK 成立。"""
    title = Path(path).name
    source_type = Path(path).suffix.lower().lstrip(".") or "unknown"
    with SessionLocal() as s:
        s.execute(text("""
            INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status)
            VALUES (:id, :ws, :title, :stype, :path, 'processing')
            ON CONFLICT (id) DO UPDATE SET status = 'processing'
        """), {"id": doc_id, "ws": workspace_id, "title": title,
               "stype": source_type, "path": path})
        s.commit()


def _mark_document_status(doc_id: uuid.UUID, status: str, error_message: str | None = None) -> None:
    with SessionLocal() as s:
        s.execute(text(
            "UPDATE documents SET status = :status, error_message = :err WHERE id = :id"
        ), {"status": status, "err": error_message, "id": doc_id})
        s.commit()


def run_ingestion(
    path: str,
    document_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """解析→切块→向量化→入库。返回 document_id。

    workspace_id 缺省时自动解析/创建默认 workspace；失败时把
    documents.status 标记为 failed 并重抛，由 RQ 记录任务失败。
    """
    doc_id = document_id or uuid.uuid4()
    if workspace_id is None:
        workspace_id = _resolve_workspace_id()
    _upsert_document(doc_id, workspace_id, path)
    try:
        pages = parse(path)
        embedder = get_embedding()
        store = VectorStore()
        chunk_idx = 0
        for page in pages:
            chunks = recursive_chunk(page.text)
            for c in chunks:
                vec = embedder.embed_documents([c])[0]
                store.add_chunk(doc_id, c, chunk_idx, page.page_number, vec)
                chunk_idx += 1
        _mark_document_status(doc_id, "completed")
    except Exception as e:
        _mark_document_status(doc_id, "failed", str(e))
        raise
    return doc_id
