import hashlib
import uuid
from pathlib import Path

from sqlalchemy import text

from app.core.config import settings
from app.db import SessionLocal
from app.generation.providers import get_embedding
from app.ingestion.chunkers.clause_aware import clause_aware_chunk
from app.ingestion.chunkers.recursive import recursive_chunk
from app.ingestion.parsers.registry import parse
from app.retrieval.vector_store import VectorStore
from app.services.context import default_workspace_id

# 批量向量化的窗口大小：每批送入 embedding 的文本数。
# 太大占内存，太小丢批处理收益；256 在 CPU 环境下是稳妥取值。
_EMBED_WINDOW = 256


class NoTextExtractedError(ValueError):
    """文档未提取出任何 chunk（如扫描件）。str() 供上层/测试匹配，入库文案走 failure_message。"""

    def __init__(self):
        super().__init__("no text extracted")
        self.failure_message = "未能提取文本，可能是扫描件"


def _chunk(text: str) -> list[dict]:
    """按配置的切块器切分，统一返回 [{"content","section_title"}]。

    条款感知切块直接产出 section_title；通用递归切块只产出文本，
    此处补齐 section_title=None 以对齐下游契约。
    """
    if settings.chunker == "recursive":
        return [{"content": c, "section_title": None}
                for c in recursive_chunk(text, settings.chunk_size, settings.chunk_overlap)]
    return clause_aware_chunk(text, settings.chunk_size, settings.chunk_overlap,
                              settings.chunk_min_size)


def _file_sha256(path: str) -> str | None:
    """原始文件字节的 sha256；文件不存在/不可读时返回 None（去重是尽力而为）。"""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _upsert_document(doc_id: uuid.UUID, workspace_id: uuid.UUID, path: str) -> None:
    """先落 documents 行，保证 add_chunk 插入 document_permissions 时 FK 成立。"""
    title = Path(path).name
    # 上传文件按 f"{doc_id}_{filename}" 落盘，展示标题剥离 uuid 前缀
    prefix = f"{doc_id}_"
    if title.startswith(prefix):
        title = title[len(prefix):]
    source_type = Path(path).suffix.lower().lstrip(".") or "unknown"
    with SessionLocal() as s:
        # 哈希只在新建行时写入：上传接口已算过一遍，此处覆盖 CLI / 重新接入等入口。
        # ON CONFLICT 分支只翻转 status，不动 content_hash，避免重复计算。
        s.execute(text("""
            INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status, content_hash)
            VALUES (:id, :ws, :title, :stype, :path, 'processing', :hash)
            ON CONFLICT (id) DO UPDATE SET status = 'processing'
        """), {"id": doc_id, "ws": workspace_id, "title": title,
               "stype": source_type, "path": path, "hash": _file_sha256(path)})
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
    roles: list[str] | None = None,
) -> uuid.UUID:
    """解析→切块→向量化→批量入库。返回 document_id。

    workspace_id 缺省时自动解析/创建默认 workspace；roles 指定文档可见角色
    （缺省全角色开放）。失败时把 documents.status 标记为 failed、清空残留
    chunk 并重抛，由 RQ 记录任务失败。
    """
    doc_id = document_id or uuid.uuid4()
    if workspace_id is None:
        workspace_id = default_workspace_id()
    _upsert_document(doc_id, workspace_id, path)
    try:
        pages = parse(path)
        embedder = get_embedding()
        store = VectorStore()
        # 重复摄取同一 doc_id：先清空旧 chunk，从干净状态开始，避免重复累计。
        _delete_chunks(doc_id)

        # 先把全文档切完块，再统一批量向量化。
        # 旧实现每切一块就调一次 embed_documents([c])，实测慢 1.6x（120 块：40.1s → 25.6s）。
        texts: list[str] = []
        page_numbers: list[int] = []
        section_titles: list[str | None] = []
        for page in pages:
            for item in _chunk(page.text):
                texts.append(item["content"])
                page_numbers.append(page.page_number)
                section_titles.append(item["section_title"])

        if not texts:
            raise NoTextExtractedError()

        # 分窗口批量编码：既有批处理加速，又避免超长文档一次性占满内存。
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_WINDOW):
            vectors.extend(embedder.embed_documents(texts[start:start + _EMBED_WINDOW]))

        if len(vectors) != len(texts):
            raise RuntimeError(f"向量化结果数量不符：{len(vectors)} != {len(texts)}")

        batch = [
            {
                "content": t,
                "chunk_index": i,
                "page_number": p,
                "section_title": s,
                "embedding": v,
            }
            for i, (t, p, s, v) in enumerate(zip(texts, page_numbers, section_titles, vectors))
        ]
        # 单事务批量入库：任一失败整体回滚，不产生孤儿 chunk。
        store.add_chunks(doc_id, batch, roles=roles)
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
