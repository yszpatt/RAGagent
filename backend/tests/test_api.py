import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app

client = TestClient(app)

# chunks.embedding 列为 vector(1024)，测试插入需要合法维度的字面量
EMB_1024 = "[" + ",".join(["0.1"] * 1024) + "]"


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_requires_file():
    r = client.post("/api/v1/documents/upload")
    assert r.status_code == 422


def test_upload_success(monkeypatch, tmp_path):
    # stub enqueue_ingestion：避免测试依赖 redis 服务
    def fake_enqueue(path, document_id, workspace_id=None, roles=None):
        assert path.startswith("/tmp/kp_uploads/")
        return SimpleNamespace(id="job-123")

    monkeypatch.setattr("app.api.v1.documents.enqueue_ingestion", fake_enqueue)

    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["document_id"]
    assert data["job_id"] == "job-123"
    assert data["status"] == "pending"


def test_chat_endpoint(monkeypatch):
    # stub get_query_graph：避免测试加载 bge 模型 / 连接数据库
    class FakeGraph:
        def invoke(self, state):
            assert state["roles"] == ["admin", "manager", "employee"]
            return {
                "answer": "假答案",
                "no_answer": False,
                "citations": [{"chunk_id": "1", "page": 1}],
            }

    monkeypatch.setattr("app.api.v1.chat.get_query_graph", lambda: FakeGraph())

    r = client.post("/api/v1/chat", json={"query": "测试"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "假答案"
    assert data["no_answer"] is False
    assert data["citations"] == [{"chunk_id": "1", "page": 1}]


def test_conversations_endpoint_shape():
    r = client.get("/api/v1/conversations")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["data"], list)
    assert "total" in body["meta"]


def test_conversations_roundtrip(engine):
    from app.api.v1.conversations import append_message, create_conversation

    conv_id = create_conversation("测试会话")
    try:
        append_message(conv_id, "user", "问题内容")
        append_message(conv_id, "assistant", "回答内容",
                       citations=[{"chunk_id": "x", "page": 1}], no_answer=False)

        r = client.get("/api/v1/conversations")
        assert r.status_code == 200
        row = next(c for c in r.json()["data"] if c["id"] == str(conv_id))
        assert row["title"] == "测试会话"
        assert row["message_count"] == 2

        r2 = client.get(f"/api/v1/conversations/{conv_id}/messages")
        assert r2.status_code == 200
        msgs = r2.json()["data"]
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[0]["content"] == "问题内容"
        assert msgs[1]["citations"] == [{"chunk_id": "x", "page": 1}]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM conversations WHERE id = :id"),
                         {"id": str(conv_id)})


def test_conversations_messages_404():
    r = client.get(f"/api/v1/conversations/{uuid.uuid4()}/messages")
    assert r.status_code == 404


def test_chat_persists_messages(engine, monkeypatch):
    class FakeGraph:
        def invoke(self, state):
            return {
                "answer": "持久化答案",
                "no_answer": False,
                "citations": [{"chunk_id": "1", "page": 1}],
            }

    monkeypatch.setattr("app.api.v1.chat.get_query_graph", lambda: FakeGraph())

    r = client.post("/api/v1/chat", json={"query": "持久化问题"})
    assert r.status_code == 200
    data = r.json()
    conv_id, msg_id = data["conversation_id"], data["message_id"]
    assert conv_id and msg_id

    r2 = client.get(f"/api/v1/conversations/{conv_id}/messages")
    msgs = r2.json()["data"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[0]["content"] == "持久化问题"
    assert msgs[1]["content"] == "持久化答案"
    assert msgs[1]["id"] == msg_id

    # 带 conversation_id 续聊 → 消息进入同一会话
    r3 = client.post("/api/v1/chat",
                     json={"query": "追问", "conversation_id": conv_id})
    assert r3.json()["conversation_id"] == conv_id
    r4 = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert len(r4.json()["data"]) == 4

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM conversations WHERE id = :id"),
                     {"id": conv_id})


def test_chat_missing_query_returns_422():
    r = client.post("/api/v1/chat", json={})
    assert r.status_code == 422


def test_chat_empty_query_returns_422():
    r = client.post("/api/v1/chat", json={"query": ""})
    assert r.status_code == 422


def test_upload_blocks_path_traversal(monkeypatch, tmp_path):
    # stub enqueue_ingestion：捕获实际写入路径，验证未被穿越到 UPLOAD_DIR 之外
    captured = {}

    def fake_enqueue(path, document_id, workspace_id=None, roles=None):
        captured["path"] = path
        return SimpleNamespace(id="job-456")

    monkeypatch.setattr("app.api.v1.documents.enqueue_ingestion", fake_enqueue)

    r = client.post(
        "/api/v1/documents/upload",
        files={"file": ("../escape.txt", b"escape", "text/plain")},
    )
    assert r.status_code == 200
    assert captured["path"].startswith("/tmp/kp_uploads/")
    # 清理后的文件名只保留 basename，且不含 ".."
    assert ".." not in captured["path"]
    assert captured["path"].endswith("_escape.txt")


def test_get_document_not_found():
    r = client.get(f"/api/v1/documents/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_document_invalid_uuid():
    r = client.get("/api/v1/documents/not-a-uuid")
    assert r.status_code == 422


def _make_doc(engine, status="completed", path="/tmp/x"):
    ws_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't')"
        ), {"id": str(ws_id)})
        conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, '测试文档', 'test', :path, :status)"
        ), {"id": str(doc_id), "ws": str(ws_id), "path": path, "status": status})
    return ws_id, doc_id


def _cleanup_doc(engine, ws_id, doc_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": str(doc_id)})
        conn.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(ws_id)})


def test_get_document_found(engine):
    ws_id, doc_id = _make_doc(engine)
    try:
        r = client.get(f"/api/v1/documents/{doc_id}")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["document_id"] == str(doc_id)
        assert data["title"] == "测试文档"
        assert data["status"] == "completed"
        assert data["error_message"] is None
        assert data["created_at"]
    finally:
        _cleanup_doc(engine, ws_id, doc_id)


def test_list_documents_contains_roles_and_chunks(engine):
    ws_id, doc_id = _make_doc(engine)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO document_permissions (id, document_id, role) "
                "VALUES (:id, :doc, 'manager')"
            ), {"id": str(uuid.uuid4()), "doc": str(doc_id)})
            conn.execute(text(
                "INSERT INTO chunks (id, document_id, content, chunk_index, token_count, embedding) "
                "VALUES (:id, :doc, '内容', 0, 2, :emb)"
            ), {"id": str(uuid.uuid4()), "doc": str(doc_id), "emb": EMB_1024})
        r = client.get("/api/v1/documents")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["total"] >= 1
        row = next(d for d in body["data"] if d["document_id"] == str(doc_id))
        assert row["title"] == "测试文档"
        assert row["roles"] == ["manager"]
        assert row["chunk_count"] == 1
    finally:
        _cleanup_doc(engine, ws_id, doc_id)


def test_delete_document_cascades(engine):
    ws_id, doc_id = _make_doc(engine)
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO chunks (id, document_id, content, chunk_index, token_count, embedding) "
                "VALUES (:id, :doc, '内容', 0, 2, :emb)"
            ), {"id": str(uuid.uuid4()), "doc": str(doc_id), "emb": EMB_1024})
        r = client.delete(f"/api/v1/documents/{doc_id}")
        assert r.status_code == 200
        assert r.json()["data"]["deleted"] is True
        with engine.begin() as conn:
            leftover = conn.execute(text(
                "SELECT count(*) FROM chunks WHERE document_id = :doc"
            ), {"doc": str(doc_id)}).scalar()
        assert leftover == 0
        assert client.get(f"/api/v1/documents/{doc_id}").status_code == 404
    finally:
        _cleanup_doc(engine, ws_id, doc_id)


def test_reingest_missing_file_returns_422(engine):
    ws_id, doc_id = _make_doc(engine, path="/tmp/kp_definitely_missing_file.txt")
    try:
        r = client.post(f"/api/v1/documents/{doc_id}/reingest")
        assert r.status_code == 422
        assert "重新上传" in r.json()["detail"]
    finally:
        _cleanup_doc(engine, ws_id, doc_id)


def test_reingest_enqueues_with_same_doc_id(engine, monkeypatch, tmp_path):
    f = tmp_path / "again.txt"
    f.write_text("重新解析")
    ws_id, doc_id = _make_doc(engine, path=str(f))
    try:
        captured = {}

        def fake_enqueue(path, document_id, workspace_id=None, roles=None):
            captured["path"] = path
            captured["document_id"] = document_id
            return SimpleNamespace(id="job-re")

        monkeypatch.setattr("app.api.v1.documents.enqueue_ingestion", fake_enqueue)
        r = client.post(f"/api/v1/documents/{doc_id}/reingest")
        assert r.status_code == 200
        assert r.json()["status"] == "processing"
        assert captured["document_id"] == doc_id
        assert captured["path"] == str(f)
        with engine.begin() as conn:
            status = conn.execute(text(
                "SELECT status FROM documents WHERE id = :id"
            ), {"id": str(doc_id)}).scalar()
        assert status == "processing"
    finally:
        _cleanup_doc(engine, ws_id, doc_id)


def test_reingest_unknown_doc_returns_404():
    r = client.post(f"/api/v1/documents/{uuid.uuid4()}/reingest")
    assert r.status_code == 404


def test_update_permissions_forces_admin(engine):
    ws_id, doc_id = _make_doc(engine)
    try:
        r = client.put(f"/api/v1/documents/{doc_id}/permissions",
                       json={"roles": ["manager", "employee"]})
        assert r.status_code == 200
        roles = r.json()["data"]["roles"]
        assert roles == ["admin", "employee", "manager"]  # 管理员强制保留

        with engine.begin() as conn:
            rows = conn.execute(text(
                "SELECT role FROM document_permissions WHERE document_id = :doc"
            ), {"doc": str(doc_id)}).fetchall()
        assert {x[0] for x in rows} == {"admin", "employee", "manager"}

        # 非法角色 → 422；空列表 → 422
        assert client.put(f"/api/v1/documents/{doc_id}/permissions",
                          json={"roles": ["boss"]}).status_code == 422
        assert client.put(f"/api/v1/documents/{doc_id}/permissions",
                          json={"roles": []}).status_code == 422
    finally:
        _cleanup_doc(engine, ws_id, doc_id)


def test_update_permissions_unknown_doc_404():
    r = client.put(f"/api/v1/documents/{uuid.uuid4()}/permissions",
                   json={"roles": ["manager"]})
    assert r.status_code == 404


def test_audit_logs_endpoint(engine):
    from app.services.audit import write_audit

    write_audit("query", query_text="审计测试问题")
    r = client.get("/api/v1/admin/audit-logs?action=query&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["total"] >= 1
    assert any(row["query_text"] == "审计测试问题" for row in body["data"])
    assert all(row["action"] == "query" for row in body["data"])


def test_metrics_endpoint(engine):
    r = client.get("/api/v1/admin/metrics")
    assert r.status_code == 200
    data = r.json()["data"]
    assert isinstance(data["today_queries"], int)
    assert isinstance(data["weekly_queries"], list)
    assert "no_answer_rate" in data and "citation_rate" in data
    assert data["acceptance_rate"] is None  # 待埋点
