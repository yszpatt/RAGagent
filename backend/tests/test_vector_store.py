import uuid
import pytest
from app.retrieval.vector_store import VectorStore


@pytest.fixture
def store():
    return VectorStore()


@pytest.fixture
def clean_tables(engine):
    # 清空依赖表（FK 顺序），保证测试隔离
    from sqlalchemy import text
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


def test_add_and_search(store, engine, clean_tables):
    from sqlalchemy import text
    with engine.begin() as conn:
        ws_id = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        doc_id = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc', 'txt', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_id)}).scalar()

    store.add_chunk(doc_id, "测试内容A", 0, 1, [-0.1] * 1024)
    store.add_chunk(doc_id, "测试内容B", 1, 2, [0.9] * 1024)

    results = store.search([0.9] * 1024, top_k=1)
    assert results[0]["content"] == "测试内容B"
    assert results[0]["page_number"] == 2


def test_search_respects_role_filter(store, engine, clean_tables):
    from sqlalchemy import text
    with engine.begin() as conn:
        ws_id = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        doc_id = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc', 'txt', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_id)}).scalar()

    store.add_chunk(doc_id, "机密内容", 0, 1, [0.5] * 1024, roles=["manager"])
    results = store.search([0.5] * 1024, top_k=5, roles=["employee"])
    assert results == []  # employee 不可见 manager 文档


def test_search_workspace_scoped(store, engine, clean_tables):
    from sqlalchemy import text
    with engine.begin() as conn:
        ws_a = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 'a') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        ws_b = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 'b') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        doc_a = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc', 'txt', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_a)}).scalar()
        doc_b = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc', 'txt', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_b)}).scalar()

    store.add_chunk(doc_a, "A工作区内容", 0, 1, [0.2] * 1024)
    store.add_chunk(doc_b, "B工作区内容", 0, 1, [0.8] * 1024)

    results = store.search([0.2] * 1024, top_k=5, workspace_id=ws_a)
    assert len(results) == 1
    assert results[0]["content"] == "A工作区内容"


def test_search_empty_roles_returns_nothing(store, engine, clean_tables):
    from sqlalchemy import text
    with engine.begin() as conn:
        ws_id = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        doc_id = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc', 'txt', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_id)}).scalar()
    store.add_chunk(doc_id, "内容", 0, 1, [0.3] * 1024)
    assert store.search([0.3] * 1024, roles=[]) == []


def test_search_top_k_limits_results(store, engine, clean_tables):
    from sqlalchemy import text
    with engine.begin() as conn:
        ws_id = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        doc_id = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, 'doc', 'txt', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_id)}).scalar()
    store.add_chunk(doc_id, "内容1", 0, 1, [0.1] * 1024)
    store.add_chunk(doc_id, "内容2", 1, 1, [0.2] * 1024)
    store.add_chunk(doc_id, "内容3", 2, 1, [0.3] * 1024)
    results = store.search([0.3] * 1024, top_k=2)
    assert len(results) == 2
    assert results[0]["content"] == "内容3"  # 最近


def test_fetch_chunk_details(store, engine, clean_tables):
    from sqlalchemy import text
    with engine.begin() as conn:
        ws_id = conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't') RETURNING id"
        ), {"id": str(uuid.uuid4())}).scalar()
        doc_id = conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, '供应商框架协议', 'pdf', '/tmp/x', 'completed') RETURNING id"
        ), {"id": str(uuid.uuid4()), "ws": str(ws_id)}).scalar()

    store.add_chunk(doc_id, "违约金为合同总价款的10%，" + "细则。" * 150, 0, 7, [0.5] * 1024)
    results = store.search([0.5] * 1024, top_k=1)
    chunk_id = str(results[0]["id"])

    details = store.fetch_chunk_details([chunk_id, "not-a-uuid"])
    assert chunk_id in details
    d = details[chunk_id]
    assert d["page"] == 7
    assert "违约金" in d["excerpt"]
    assert d["excerpt"].endswith("…")  # 超 200 字截断
    assert d["document_title"] == "供应商框架协议"

    # 查不到 / 非法 / 空输入 → 空结果
    assert store.fetch_chunk_details([uuid.uuid4()]) == {}
    assert store.fetch_chunk_details(["not-a-uuid"]) == {}
    assert store.fetch_chunk_details([]) == {}
