import os
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def engine():
    url = os.environ.get("TEST_DATABASE_URL", "postgresql://kp:kp@localhost:5432/knowledgepilot")
    return create_engine(url)


def test_schema_tables_exist(engine):
    with engine.connect() as conn:
        tables = conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"
        )).fetchall()
        names = {t[0] for t in tables}
        required = {"documents", "chunks", "document_permissions",
                    "conversations", "messages", "audit_logs", "ingestion_jobs"}
        assert required.issubset(names)


def test_pgvector_extension_installed(engine):
    with engine.connect() as conn:
        ext = conn.execute(text("SELECT extname FROM pg_extension")).fetchall()
        assert ("vector",) in ext


def test_chunk_vector_dimension_enforced(engine):
    import uuid

    ws_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    bad_vec = [0.1] * 128  # wrong dim: chunks.embedding is Vector(1024)
    raised = False
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # create real workspace + document rows so only the vector-dimension
            # check can fail; everything rolls back in finally
            conn.execute(text(
                "INSERT INTO workspaces (id, name) VALUES (:id, 't')"
            ), {"id": ws_id})
            conn.execute(text(
                "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
                "VALUES (:id, :ws, 't', 'test', '/tmp/x', 'pending')"
            ), {"id": doc_id, "ws": ws_id})
            try:
                conn.execute(text(
                    "INSERT INTO chunks (id, document_id, content, chunk_index, token_count, embedding) "
                    "VALUES (:id, :doc, 'x', 0, 1, :emb)"
                ), {"id": str(uuid.uuid4()), "doc": doc_id, "emb": bad_vec})
            except Exception:
                raised = True
        finally:
            trans.rollback()
    assert raised, "inserting a 128-dim vector into a 1024-dim column must raise"
