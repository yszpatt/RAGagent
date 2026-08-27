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
        conn.execute(text("DELETE FROM chunks"))
        conn.execute(text("DELETE FROM document_permissions"))
        conn.execute(text("DELETE FROM documents"))
        conn.execute(text("DELETE FROM users"))
        conn.execute(text("DELETE FROM workspaces"))
    yield
    with engine.begin() as conn:
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
