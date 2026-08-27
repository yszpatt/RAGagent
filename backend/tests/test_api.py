import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_requires_file():
    r = client.post("/api/v1/documents/upload")
    assert r.status_code == 422


def test_upload_success(monkeypatch, tmp_path):
    # stub enqueue_ingestion：避免测试依赖 redis 服务
    def fake_enqueue(path, document_id, workspace_id=None):
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


def test_conversations_empty():
    r = client.get("/api/v1/conversations")
    assert r.status_code == 200
    assert r.json() == {"data": [], "meta": {"total": 0}}


def test_chat_missing_query_returns_422():
    r = client.post("/api/v1/chat", json={})
    assert r.status_code == 422


def test_chat_empty_query_returns_422():
    r = client.post("/api/v1/chat", json={"query": ""})
    assert r.status_code == 422


def test_upload_blocks_path_traversal(monkeypatch, tmp_path):
    # stub enqueue_ingestion：捕获实际写入路径，验证未被穿越到 UPLOAD_DIR 之外
    captured = {}

    def fake_enqueue(path, document_id, workspace_id=None):
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


def test_get_document_found(engine):
    ws_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO workspaces (id, name) VALUES (:id, 't')"
        ), {"id": str(ws_id)})
        conn.execute(text(
            "INSERT INTO documents (id, workspace_id, title, source_type, storage_path, status) "
            "VALUES (:id, :ws, '测试文档', 'test', '/tmp/x', 'completed')"
        ), {"id": str(doc_id), "ws": str(ws_id)})
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
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM documents WHERE id = :id"), {"id": str(doc_id)})
            conn.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(ws_id)})
