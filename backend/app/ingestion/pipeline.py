import uuid
from pathlib import Path

from sqlalchemy import text

from app.db import SessionLocal
from app.generation.providers import get_embedding
from app.ingestion.chunkers.recursive import recursive_chunk
from app.ingestion.parsers.registry import parse
from app.retrieval.vector_store import VectorStore

DEFAULT_WORKSPACE_NAME = "默认工作区"


class NoTextExtractedError(ValueError):
    """文档未提取出任何 chunk（如扫描件）。str() 供上层/测试匹配，入库文案走 failure_message。"""

    def __init__(self):
        super().__init__("no text extracted")
        self.failure_message = "未能提取文本，可能是扫描件"


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


def _delete_chunks(doc_id: uuid.UUID) -> None:
    """清空某文档的全部 chunk，用于失败清理与重复摄取前的干净起点。"""
    with SessionLocal() as s:
        s.execute(text(
            "DELETE FROM chunks WHERE document_id = :doc"
        ), {"doc": doc_id})
        s.commit()


def run_ingestion(
    path: str,
    document_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """解析→切块→向量化→批量入库。返回 document_id。

    workspace_id 缺省时自动解析/创建默认 workspace；失败时把
    documents.status 标记为 failed、清空残留 chunk 并重抛，由 RQ 记录任务失败。
    """
    doc_id = document_id or uuid.uuid4()
    if workspace_id is None:
        workspace_id = _resolve_workspace_id()
    _upsert_document(doc_id, workspace_id, path)
    try:
        pages = parse(path)
        embedder = get_embedding()
        store = VectorStore()
        # 重复摄取同一 doc_id：先清空旧 chunk，从干净状态开始，避免重复累计。
        _delete_chunks(doc_id)
        batch = []
        for page in pages:
            for c in recursive_chunk(page.text):
                vec = embedder.embed_documents([c])[0]
                batch.append({
                    "content": c,
                    "chunk_index": len(batch),
                    "page_number": page.page_number,
                    "embedding": vec,
                })
        if len(batch) == 0:
            raise NoTextExtractedError()
        # 单事务批量入库：任一失败整体回滚，不产生孤儿 chunk。
        store.add_chunks(doc_id, batch)
        _mark_document_status(doc_id, "completed")
    except Exception as e:
        # 状态写入与清理都可能在 DB 本身宕机时失败：保护之，确保原始异常被重抛。
        try:
            _mark_document_status(doc_id, "failed", getattr(e, "failure_message", None) or str(e))
        except Exception:
            pass
        try:
            _delete_chunks(doc_id)
        except Exception:
            pass
        raise
    return doc_id
