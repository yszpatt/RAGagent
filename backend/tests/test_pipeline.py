import uuid

import pytest
from sqlalchemy import text

from app.ingestion.pipeline import run_ingestion


class FakeEmbedder:
    """1024 维伪 embedder，避免测试加载 bge-m3（~2GB）。"""

    def embed_documents(self, texts):
        return [[0.1] * 1024 for _ in texts]

    def embed_query(self, text_):
        return [0.1] * 1024


@pytest.fixture
def fake_embedding(monkeypatch):
    monkeypatch.setattr("app.ingestion.pipeline.get_embedding", lambda: FakeEmbedder())


@pytest.fixture
def clean_tables(engine):
    # 清空依赖表（FK 顺序），保证测试隔离
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_logs"))
        conn.execute(text("DELETE FROM messages"))
        conn.execute(text("DELETE FROM conversations"))
        conn.execute(text("DELETE FROM chunks"))
        conn.execute(text("DELETE FROM document_permissions"))
        conn.execute(text("DELETE FROM documents"))
        conn.execute(text("DELETE FROM users"))
        conn.execute(text("DELETE FROM workspaces"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_logs"))
        conn.execute(text("DELETE FROM messages"))
        conn.execute(text("DELETE FROM conversations"))
        conn.execute(text("DELETE FROM chunks"))
        conn.execute(text("DELETE FROM document_permissions"))
        conn.execute(text("DELETE FROM documents"))
        conn.execute(text("DELETE FROM users"))
        conn.execute(text("DELETE FROM workspaces"))


def test_run_ingestion_returns_document_id(tmp_path, fake_embedding, clean_tables):
    f = tmp_path / "doc.txt"
    f.write_text("这是测试文档内容。" * 10, encoding="utf-8")
    doc_id = run_ingestion(str(f))
    assert isinstance(doc_id, uuid.UUID)


def test_run_ingestion_accepts_existing_document_id(tmp_path, fake_embedding, clean_tables):
    f = tmp_path / "doc.txt"
    f.write_text("内容", encoding="utf-8")
    doc_id = uuid.uuid4()
    result = run_ingestion(str(f), document_id=doc_id)
    assert result == doc_id


def test_run_ingestion_creates_completed_document_row(tmp_path, fake_embedding, clean_tables, engine):
    """验证 FK 处理：documents 行先落库，add_chunk 写 permissions 不炸 FK，最终状态 completed。"""
    f = tmp_path / "doc.txt"
    f.write_text("内容", encoding="utf-8")
    doc_id = run_ingestion(str(f))
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT status, source_type, title FROM documents WHERE id = :id"
        ), {"id": str(doc_id)}).fetchone()
        chunk_count = conn.execute(text(
            "SELECT COUNT(*) FROM chunks WHERE document_id = :id"
        ), {"id": str(doc_id)}).scalar()
    assert row is not None
    assert row[0] == "completed"
    assert row[1] == "txt"
    assert row[2] == "doc.txt"
    assert chunk_count >= 1


def test_run_ingestion_marks_failed_on_parse_error(tmp_path, fake_embedding, clean_tables, engine):
    f = tmp_path / "doc.xyz"
    f.write_text("内容", encoding="utf-8")
    with pytest.raises(ValueError):
        run_ingestion(str(f))
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT status, error_message FROM documents WHERE title = 'doc.xyz'"
        )).fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert row[1] is not None


def test_run_ingestion_zero_chunks_marks_failed(tmp_path, fake_embedding, clean_tables, engine):
    """纯空白文件（如扫描件）产不出 chunk → 标记 failed 而非伪 completed。"""
    f = tmp_path / "blank.txt"
    f.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(ValueError, match="no text extracted"):
        run_ingestion(str(f))
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT status, error_message FROM documents WHERE title = 'blank.txt'"
        )).fetchone()
    assert row is not None
    assert row[0] == "failed"
    assert "未能提取" in (row[1] or "")


def test_run_ingestion_cleans_orphan_chunks_on_failure(tmp_path, clean_tables, engine, monkeypatch):
    """embedding 失败时：doc 标记 failed，且历史残留 chunk 被清空（不留下可检索孤儿）。"""
    f = tmp_path / "doc.txt"
    f.write_text("内容", encoding="utf-8")
    doc_id = uuid.uuid4()

    # 预置 workspace + doc + 孤儿 chunk（模拟上一次失败或历史残留）
    with engine.begin() as conn:
        ws_id = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc.txt', 'txt', '/tmp/x', 'failed')"
        ), {"id": str(doc_id), "ws": str(ws_id)})
        conn.execute(text(
            "INSERT INTO chunks (id, document_id, content, chunk_index, page_number, token_count, embedding) "
            "VALUES (:id, :doc, 'orphan', 0, 1, 6, :emb)"
        ), {"id": str(uuid.uuid4()), "doc": str(doc_id),
            "emb": "[" + ",".join(["0.1"] * 1024) + "]"})

    class RaisingEmbedder:
        def embed_documents(self, texts):
            raise RuntimeError("embedding failed")

        def embed_query(self, text_):
            raise RuntimeError("embedding failed")

    monkeypatch.setattr("app.ingestion.pipeline.get_embedding", lambda: RaisingEmbedder())

    with pytest.raises(RuntimeError, match="embedding failed"):
        run_ingestion(str(f), document_id=doc_id)

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT status, error_message FROM documents WHERE id = :id"
        ), {"id": str(doc_id)}).fetchone()
        chunk_count = conn.execute(text(
            "SELECT COUNT(*) FROM chunks WHERE document_id = :id"
        ), {"id": str(doc_id)}).scalar()
    assert row[0] == "failed"
    assert row[1] is not None
    assert chunk_count == 0


def test_run_ingestion_reingest_does_not_duplicate(tmp_path, fake_embedding, clean_tables, engine):
    """同一 doc_id 重复摄取：先清旧 chunk 再入库，chunk 数不累计重复。"""
    f = tmp_path / "doc.txt"
    f.write_text("这是测试文档内容。" * 100, encoding="utf-8")  # 超 chunk_size，产多个 chunk
    doc_id = uuid.uuid4()
    run_ingestion(str(f), document_id=doc_id)
    with engine.connect() as conn:
        first_count = conn.execute(text(
            "SELECT COUNT(*) FROM chunks WHERE document_id = :id"
        ), {"id": str(doc_id)}).scalar()
    assert first_count > 1

    run_ingestion(str(f), document_id=doc_id)  # 重新摄取同一文档
    with engine.connect() as conn:
        second_count = conn.execute(text(
            "SELECT COUNT(*) FROM chunks WHERE document_id = :id"
        ), {"id": str(doc_id)}).scalar()
        status = conn.execute(text(
            "SELECT status FROM documents WHERE id = :id"
        ), {"id": str(doc_id)}).scalar()
    assert status == "completed"
    assert second_count == first_count  # 不重复累计
