from types import SimpleNamespace

from fastapi.testclient import TestClient
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
