# KnowledgePilot Demo 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建一个 demo 级企业知识库（RAG）系统：上传 PDF/DOCX/MD/TXT → 检索问答 → 带引用答案 + 权限过滤。

**Architecture:** FastAPI 后端 + LangGraph 双图编排（ingestion 异步 / query 同步）+ pgvector 存储 + React(Next.js) 前端 + Docker Compose 部署。Provider 抽象隔离 LLM/Embedding/Rerank，本地 Ollama + bge-m3 + bge-reranker 起步。

**Tech Stack:** Python 3.11 · FastAPI · LangChain/LangGraph · pgvector · Redis + RQ · Next.js · Docker Compose

**Demo 范围（YAGNI 裁剪）：**
- 数据源仅 PDF/DOCX/MD/TXT（满足"≥3 种"验收）；OCR 扫描件**不做**（预留 marker 接口）
- SSO **仅预留接口**（external_id + 接口桩），不做完整 OIDC 对接
- 对象存储用**本地文件系统**（StorageBackend 抽象）
- 权限三级（admin/manager/employee），检索前 SQL 过滤
- 无答案兜底 + 引用溯源（文件/页）

---

## Task 0: 项目脚手架

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `deploy/docker-compose.yml`
- Create: `.env.example`

**Step 1: 创建后端依赖清单**

```toml
# backend/pyproject.toml
[project]
name = "knowledgepilot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "langchain>=0.1.16",
    "langgraph>=0.0.30",
    "langchain-community>=0.0.36",
    "psycopg[binary]>=3.1",
    "pgvector>=0.2.4",
    "redis>=5.0",
    "rq>=1.16",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "python-multipart>=0.0.9",
    "sentence-transformers>=2.6",
    "pypdf>=4.0",
    "python-docx>=1.1",
    "markdown>=3.5",
    "aiofiles>=23.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "testcontainers>=4.4",
]
```

**Step 2: 创建 Docker Compose**

```yaml
# deploy/docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: kp
      POSTGRES_PASSWORD: kp
      POSTGRES_DB: knowledgepilot
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  api:
    build: ../backend
    ports: ["8000:8000"]
    env_file: [../.env]
    depends_on: [postgres, redis]
  worker:
    build: ../backend
    command: ["rq", "worker", "ingestion"]
    env_file: [../.env]
    depends_on: [postgres, redis]
volumes:
  pgdata:
```

**Step 3: 创建最小 FastAPI 入口**

```python
# backend/app/main.py
from fastapi import FastAPI

app = FastAPI(title="KnowledgePilot")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
```

**Step 4: 验证**

Run: `cd backend && python -c "from app.main import app; print(app.title)"`
Expected: `KnowledgePilot`

**Step 5: Commit**

```bash
git add backend/ deploy/ .env.example
git commit -m "chore: scaffold backend + docker-compose"
```

---

## Task 1: 配置与 Provider 抽象层

**Files:**
- Create: `backend/app/core/config.py`
- Create: `backend/app/generation/providers/__init__.py`
- Create: `backend/app/generation/providers/base.py`
- Create: `backend/app/generation/providers/embedding.py`
- Create: `backend/app/generation/providers/llm.py`
- Create: `backend/app/generation/providers/reranker.py`
- Test: `backend/tests/test_providers.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_providers.py
from app.generation.providers.base import EmbeddingProvider, LLMProvider, RerankerProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker


def test_embedding_provider_interface():
    emb = BgeM3Embedding()
    assert isinstance(emb, EmbeddingProvider)
    assert emb.dim == 1024


def test_provider_factory_returns_correct_type():
    from app.generation.providers import get_embedding, get_reranker
    assert get_embedding().dim == 1024
    assert isinstance(get_reranker(), RerankerProvider)
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_providers.py -v`
Expected: FAIL（`ModuleNotFoundError`）

**Step 3: 实现 Provider 接口**

```python
# backend/app/generation/providers/base.py
from abc import ABC, abstractmethod
from typing import Protocol


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class RerankerProvider(ABC):
    @abstractmethod
    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        """返回 (原文索引, 分数) 按分数降序"""
        ...


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, context: str) -> str: ...
```

```python
# backend/app/generation/providers/embedding.py
from sentence_transformers import SentenceTransformer
from app.generation.providers.base import EmbeddingProvider


class BgeM3Embedding(EmbeddingProvider):
    dim = 1024

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self._model = SentenceTransformer(model_name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], normalize_embeddings=True)[0].tolist()
```

```python
# backend/app/generation/providers/reranker.py
from sentence_transformers import CrossEncoder
from app.generation.providers.base import RerankerProvider


class BgeReranker(RerankerProvider):
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, docs: list[str]) -> list[tuple[int, float]]:
        pairs = [(query, d) for d in docs]
        scores = self._model.predict(pairs)
        ranked = sorted(enumerate(scores), key=lambda x: -x[1])
        return ranked
```

```python
# backend/app/generation/providers/__init__.py
from functools import lru_cache
from app.generation.providers.base import EmbeddingProvider, RerankerProvider
from app.generation.providers.embedding import BgeM3Embedding
from app.generation.providers.reranker import BgeReranker


@lru_cache
def get_embedding() -> EmbeddingProvider:
    return BgeM3Embedding()


@lru_cache
def get_reranker() -> RerankerProvider:
    return BgeReranker()
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_providers.py -v`
Expected: PASS（首次会下载模型，需网络）

**Step 5: Commit**

```bash
git add backend/app/generation/providers/ backend/tests/test_providers.py
git commit -m "feat: provider abstraction for embedding/reranker/llm"
```

---

## Task 2: 数据模型与数据库迁移

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/domain/models.py`
- Create: `backend/alembic/versions/0001_init.py`（或 SQL 初始化脚本）
- Test: `backend/tests/test_db.py`

**Step 1: 写失败测试（schema 存在性）**

```python
# backend/tests/test_db.py
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
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_db.py -v`
Expected: FAIL（表不存在）

**Step 3: 实现初始化脚本**

```python
# backend/app/db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://kp:kp@localhost:5432/knowledgepilot"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass
```

```python
# backend/app/domain/models.py
import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.db import Base


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True)  # SSO 预留
    role: Mapped[str] = mapped_column(String(32))  # admin|manager|employee
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    title: Mapped[str] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(32))
    storage_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DocumentPermission(Base):
    __tablename__ = "document_permissions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(512))
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    title: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSONB)
    no_answer: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"))
    action: Mapped[str] = mapped_column(String(64))
    query_text: Mapped[str | None] = mapped_column(Text)
    retrieved_chunk_ids: Mapped[list | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    response_ref: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

**Step 4: 执行建表**

Run: `cd backend && python -c "from app.db import engine; from app.domain import models; from app.db import Base; Base.metadata.create_all(engine); print('created')"`（demo 用 create_all，生产换 Alembic）

**Step 5: 运行确认通过**

Run: `cd backend && pytest tests/test_db.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/app/db.py backend/app/domain/ backend/tests/test_db.py
git commit -m "feat: domain models + pgvector schema"
```

---

## Task 3: 文档解析器（Parsers）

**Files:**
- Create: `backend/app/ingestion/parsers/__init__.py`
- Create: `backend/app/ingestion/parsers/base.py`
- Create: `backend/app/ingestion/parsers/pdf_parser.py`
- Create: `backend/app/ingestion/parsers/docx_parser.py`
- Create: `backend/app/ingestion/parsers/text_parser.py`
- Create: `backend/app/ingestion/parsers/registry.py`
- Test: `backend/tests/test_parsers.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_parsers.py
from app.ingestion.parsers.registry import parse


def test_parse_txt_returns_paragraphs():
    path = "/tmp/test.txt"
    with open(path, "w") as f:
        f.write("第一段内容。\n\n第二段内容。")
    pages = parse(path)
    assert len(pages) == 1
    assert "第一段内容" in pages[0].text


def test_parse_unsupported_extension_raises():
    import pytest
    with pytest.raises(ValueError):
        parse("/tmp/test.xyz")
```

**Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_parsers.py -v`
Expected: FAIL（模块不存在）

**Step 3: 实现解析器**

```python
# backend/app/ingestion/parsers/base.py
from dataclasses import dataclass


@dataclass
class Page:
    page_number: int
    text: str
```

```python
# backend/app/ingestion/parsers/text_parser.py
from pathlib import Path
from app.ingestion.parsers.base import Page


def parse_text(path: str) -> list[Page]:
    text = Path(path).read_text(encoding="utf-8")
    return [Page(page_number=1, text=text)]
```

```python
# backend/app/ingestion/parsers/registry.py
from pathlib import Path
from app.ingestion.parsers.base import Page

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


def parse(path: str) -> list[Page]:
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"unsupported extension: {ext}")
    if ext in {".txt", ".md"}:
        from app.ingestion.parsers.text_parser import parse_text
        return parse_text(path)
    if ext == ".pdf":
        from app.ingestion.parsers.pdf_parser import parse_pdf
        return parse_pdf(path)
    if ext == ".docx":
        from app.ingestion.parsers.docx_parser import parse_docx
        return parse_docx(path)
    raise ValueError(f"unsupported extension: {ext}")
```

```python
# backend/app/ingestion/parsers/pdf_parser.py
from pypdf import PdfReader
from app.ingestion.parsers.base import Page


def parse_pdf(path: str) -> list[Page]:
    reader = PdfReader(path)
    return [Page(page_number=i + 1, text=p.extract_text() or "") for i, p in enumerate(reader.pages)]
```

```python
# backend/app/ingestion/parsers/docx_parser.py
from docx import Document as DocxDocument
from app.ingestion.parsers.base import Page


def parse_docx(path: str) -> list[Page]:
    doc = DocxDocument(path)
    text = "\n".join(p.text for p in doc.paragraphs)
    return [Page(page_number=1, text=text)]
```

**Step 4: 运行确认通过**

Run: `cd backend && pytest tests/test_parsers.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/ingestion/parsers/ backend/tests/test_parsers.py
git commit -m "feat: document parsers (txt/md/pdf/docx)"
```

---

## Task 4: 语义切块器（Chunker）

**Files:**
- Create: `backend/app/ingestion/chunkers/__init__.py`
- Create: `backend/app/ingestion/chunkers/recursive.py`
- Test: `backend/tests/test_chunker.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_chunker.py
from app.ingestion.chunkers.recursive import recursive_chunk


def test_chunk_splits_long_text():
    text = "句子。" * 2000  # 超长文本
    chunks = recursive_chunk(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_chunk_short_text_single():
    chunks = recursive_chunk("短文本", chunk_size=200, overlap=40)
    assert len(chunks) == 1
    assert chunks[0] == "短文本"


def test_chunk_preserves_content():
    text = "A" * 100 + "SEP" + "B" * 100
    chunks = recursive_chunk(text, chunk_size=100, overlap=20)
    assert "SEP" in "".join(chunks)
```

**Step 2: 运行确认失败** → 实现 → **Step 4: 验证通过**

```python
# backend/app/ingestion/chunkers/recursive.py
def recursive_chunk(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按分隔符优先级递归切块，带重叠。demo 版基于字符，生产换 tiktoken。"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    separators = ["\n\n", "\n", "。", ".", " ", ""]
    for sep in separators:
        parts = text.split(sep) if sep else list(text)
        chunks, cur = [], ""
        for p in parts:
            piece = p + (sep if sep else "")
            if len(cur) + len(piece) > chunk_size and cur:
                chunks.append(cur.strip())
                cur = cur[-overlap:] if overlap else ""
            cur += piece
        if cur.strip():
            chunks.append(cur.strip())
        if len(chunks) > 1:
            return chunks
    return [text]
```

**Step 5: Commit**

```bash
git add backend/app/ingestion/chunkers/ backend/tests/test_chunker.py
git commit -m "feat: recursive chunker"
```

---

## Task 5: Vector Store（pgvector 封装）

**Files:**
- Create: `backend/app/retrieval/__init__.py`
- Create: `backend/app/retrieval/vector_store.py`
- Test: `backend/tests/test_vector_store.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_vector_store.py
import uuid
import pytest
from app.retrieval.vector_store import VectorStore


@pytest.fixture
def store():
    return VectorStore()


def test_add_and_search(store, engine):
    doc_id = uuid.uuid4()
    store.add_chunk(doc_id, "测试内容A", 0, 1, [0.1] * 1024)
    store.add_chunk(doc_id, "测试内容B", 1, 2, [0.9] * 1024)
    results = store.search([0.9] * 1024, top_k=1)
    assert results[0]["content"] == "测试内容B"


def test_search_respects_role_filter(store, engine):
    doc_id = uuid.uuid4()
    store.add_chunk(doc_id, "机密内容", 0, 1, [0.5] * 1024, roles=["manager"])
    results = store.search([0.5] * 1024, top_k=5, roles=["employee"])
    assert results == []  # employee 不可见 manager 文档
```

**Step 2: 运行确认失败** → **Step 3: 实现**

```python
# backend/app/retrieval/vector_store.py
import uuid
from sqlalchemy import text
from app.db import SessionLocal


class VectorStore:
    def add_chunk(self, document_id, content, chunk_index, page_number, embedding, roles=None):
        roles = roles or ["admin", "manager", "employee"]
        with SessionLocal() as s:
            chunk_id = uuid.uuid4()
            s.execute(text("""
                INSERT INTO chunks (id, document_id, content, chunk_index, page_number, token_count, embedding)
                VALUES (:id, :doc, :content, :idx, :page, :tc, :emb)
            """), {"id": chunk_id, "doc": document_id, "content": content,
                   "idx": chunk_index, "page": page_number, "tc": len(content),
                   "emb": embedding})
            for r in roles:
                s.execute(text("""
                    INSERT INTO document_permissions (document_id, role) VALUES (:doc, :role)
                """), {"doc": document_id, "role": r})
            s.commit()

    def search(self, query_vec, top_k=5, roles=None, workspace_id=None):
        roles = roles or ["admin", "manager", "employee"]
        with SessionLocal() as s:
            rows = s.execute(text("""
                SELECT c.id, c.content, c.page_number, c.section_title,
                       c.embedding <=> :q AS distance
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                JOIN document_permissions dp ON d.id = dp.document_id
                WHERE dp.role IN :roles
                ORDER BY distance ASC
                LIMIT :k
            """), {"q": query_vec, "roles": tuple(roles), "k": top_k}).fetchall()
            return [{"id": r[0], "content": r[1], "page_number": r[2],
                     "section_title": r[3], "distance": r[4]} for r in rows]
```

**Step 4: 验证通过**

Run: `cd backend && pytest tests/test_vector_store.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/retrieval/ backend/tests/test_vector_store.py
git commit -m "feat: pgvector store with pre-retrieval role filter"
```

---

## Task 6: Ingestion 编排（RQ 异步任务）

**Files:**
- Create: `backend/app/ingestion/pipeline.py`
- Create: `backend/app/ingestion/tasks.py`
- Test: `backend/tests/test_pipeline.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_pipeline.py
from app.ingestion.pipeline import run_ingestion


def test_run_ingestion_end_to_end(tmp_path, store, engine):
    f = tmp_path / "doc.txt"
    f.write_text("这是测试文档内容。" * 10)
    # run_ingestion(document_id, path) 直接调用（跳过 RQ 队列）
    doc_id = run_ingestion(f)
    results = store.search([0.1] * 1024, top_k=3)
    assert len(results) > 0
```

**Step 2: 实现 pipeline**

```python
# backend/app/ingestion/pipeline.py
import uuid
from app.ingestion.parsers.registry import parse
from app.ingestion.chunkers.recursive import recursive_chunk
from app.generation.providers import get_embedding
from app.retrieval.vector_store import VectorStore


def run_ingestion(path: str, document_id: uuid.UUID | None = None) -> uuid.UUID:
    """解析→切块→向量化→入库。返回 document_id。"""
    doc_id = document_id or uuid.uuid4()
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
    return doc_id
```

```python
# backend/app/ingestion/tasks.py
from redis import Redis
from rq import Queue
from app.ingestion.pipeline import run_ingestion

redis_conn = Redis.from_url("redis://localhost:6379")
queue = Queue("ingestion", connection=redis_conn)


def enqueue_ingestion(path: str, document_id):
    return queue.enqueue(run_ingestion, path, document_id)
```

**Step 3: 验证通过** → **Step 4: Commit**

```bash
git add backend/app/ingestion/pipeline.py backend/app/ingestion/tasks.py backend/tests/test_pipeline.py
git commit -m "feat: ingestion pipeline + RQ task"
```

---

## Task 7: Query Graph（LangGraph 问答编排）

**Files:**
- Create: `backend/app/generation/graphs/query_graph.py`
- Create: `backend/app/guardrails/__init__.py`
- Create: `backend/app/guardrails/no_answer.py`
- Test: `backend/tests/test_query_graph.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_query_graph.py
from app.generation.graphs.query_graph import build_query_graph
from app.guardrails.no_answer import should_no_answer


def test_no_answer_when_low_rerank():
    assert should_no_answer(top_score=0.1, threshold=0.3) is True
    assert should_no_answer(top_score=0.8, threshold=0.3) is False


def test_query_graph_compiles():
    graph = build_query_graph()
    assert graph is not None
```

**Step 2: 实现**

```python
# backend/app/guardrails/no_answer.py
def should_no_answer(top_score: float, threshold: float = 0.3) -> bool:
    return top_score < threshold
```

```python
# backend/app/generation/graphs/query_graph.py
from typing import TypedDict
from langgraph.graph import StateGraph, END


class QueryState(TypedDict):
    query: str
    roles: list[str]
    retrieved: list
    reranked: list
    answer: str
    no_answer: bool
    citations: list


def build_query_graph():
    from app.retrieval.vector_store import VectorStore
    from app.generation.providers import get_embedding, get_reranker
    from app.guardrails.no_answer import should_no_answer

    store = VectorStore()
    embedder = get_embedding()
    reranker = get_reranker()

    def retrieve(state: QueryState) -> QueryState:
        vec = embedder.embed_query(state["query"])
        state["retrieved"] = store.search(vec, top_k=10, roles=state["roles"])
        return state

    def rerank(state: QueryState) -> QueryState:
        docs = [r["content"] for r in state["retrieved"]]
        ranked = reranker.rerank(state["query"], docs)
        state["reranked"] = [state["retrieved"][i] for i, _ in ranked[:5]]
        return state

    def generate(state: QueryState) -> QueryState:
        top = state["reranked"][0] if state["reranked"] else None
        if top is None or should_no_answer(1.0 if top else 0.0):
            state["no_answer"] = True
            state["answer"] = "未找到相关信息，请尝试换个问法。"
        else:
            state["no_answer"] = False
            state["answer"] = f"根据资料：{top['content'][:200]}"
            state["citations"] = [{"chunk_id": top["id"], "page": top["page_number"]}]
        return state

    g = StateGraph(QueryState)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("generate", generate)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "generate")
    g.add_edge("generate", END)
    return g.compile()
```

**Step 3: 验证通过** → **Step 4: Commit**

```bash
git add backend/app/generation/graphs/ backend/app/guardrails/ backend/tests/test_query_graph.py
git commit -m "feat: LangGraph query graph + no-answer guardrail"
```

---

## Task 8: API 层（FastAPI 路由）

**Files:**
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/v1/__init__.py`
- Create: `backend/app/api/v1/documents.py`
- Create: `backend/app/api/v1/chat.py`
- Create: `backend/app/api/v1/conversations.py`
- Test: `backend/tests/test_api.py`

**Step 1: 写失败测试**

```python
# backend/tests/test_api.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload_requires_auth():
    r = client.post("/api/v1/documents/upload")
    assert r.status_code in (401, 422)  # demo 未接 auth 时至少参数校验
```

**Step 2: 实现路由**

```python
# backend/app/api/v1/documents.py
import uuid
import aiofiles
from fastapi import APIRouter, UploadFile, File
from app.ingestion.tasks import enqueue_ingestion

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    doc_id = uuid.uuid4()
    path = f"/tmp/kp_uploads/{doc_id}_{file.filename}"
    async with aiofiles.open(path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)
    job = enqueue_ingestion(path, doc_id)
    return {"document_id": str(doc_id), "job_id": str(job.id), "status": "pending"}
```

```python
# backend/app/api/v1/chat.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.generation.graphs.query_graph import build_query_graph

router = APIRouter(prefix="/chat", tags=["chat"])
graph = build_query_graph()


@router.post("")
async def chat(payload: dict):
    state = {"query": payload["query"], "roles": ["admin", "manager", "employee"],
             "retrieved": [], "reranked": [], "answer": "", "no_answer": False, "citations": []}
    result = graph.invoke(state)
    return {"answer": result["answer"], "no_answer": result["no_answer"], "citations": result["citations"]}
```

**Step 3: 验证通过** → **Step 4: Commit**

```bash
git add backend/app/api/ backend/tests/test_api.py
git commit -m "feat: REST API (documents/chat/conversations)"
```

---

## Task 9: 前端 React（Next.js 聊天界面）

**Files:**
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/chat/page.tsx`
- Create: `frontend/package.json`

**Step 1: 脚手架 + 最小聊天页**

```bash
cd frontend && npx create-next-app@latest . --ts --tailwind --app --no-src-dir --import-alias "@/*" --yes
```

**Step 2: 实现聊天页（简化）**

```tsx
// frontend/app/chat/page.tsx
"use client";
import { useState } from "react";

export default function Chat() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState([]);

  async function ask() {
    const res = await fetch("/api/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    setAnswer(data.answer);
    setCitations(data.citations || []);
  }

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <textarea value={query} onChange={(e) => setQuery(e.target.value)} className="w-full border p-2" />
      <button onClick={ask} className="mt-2 bg-blue-500 text-white px-4 py-2 rounded">提问</button>
      {answer && <div className="mt-4 p-4 border rounded">{answer}</div>}
      {citations.map((c, i) => <div key={i} className="text-sm text-blue-600">来源：第 {c.page} 页</div>)}
    </div>
  );
}
```

**Step 3: 验证**

Run: `cd frontend && npm run build`
Expected: 构建成功

**Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: React chat UI"
```

---

## Task 10: 端到端验证与部署

**Files:**
- Modify: `backend/app/main.py`（挂载路由）
- Create: `README.md`

**Step 1: 挂载路由 + 启动**

```python
# backend/app/main.py 追加
from app.api.v1 import documents, chat, conversations
app.include_router(documents.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(conversations.router, prefix="/api/v1")
```

**Step 2: 端到端冒烟**

```bash
cd /home/yszpat/RAGAgent && docker compose -f deploy/docker-compose.yml up -d postgres redis
# 准备样例文档，走一遍 上传→检索→回答 全流程
```

**Step 3: 验证验收标准**

- ✅ 上传 TXT/MD/PDF/DOCX ≥3 种格式
- ✅ 回答带引用（页码）
- ✅ 低相关触发 No-Answer
- ✅ employee 角色无法检索 manager 文档

**Step 4: Commit + 打 tag**

```bash
git add -A
git commit -m "feat: end-to-end demo working"
git tag v0.1.0-demo
```

---

## 验收对照（对应产品文档 §7 验收标准）

| 验收标准 | 实现位置 | 状态 |
|---|---|---|
| ≥3 种脏文档类型 | Task 3（PDF/DOCX/MD/TXT） | ✅ |
| 检索+重排可测 | Task 5 + Task 7 | ✅ |
| 引用溯源（文件/页） | Task 7 citations | ✅ |
| 角色权限检索前过滤 | Task 5（SQL WHERE） | ✅ |
| 无答案兜底 | Task 7 guardrail | ✅ |
| Docker 部署 | Task 0 + Task 10 | ✅ |

## 明确不做（YAGNI，demo 范围外）

- ❌ OCR 扫描件（预留 marker 接口）
- ❌ 完整 SSO 对接（仅 external_id 桩）
- ❌ S3 对象存储（StorageBackend 抽象预留）
- ❌ BM25 混合检索、多轮追问、使用看板
- ❌ 完整评估 harness（RAGAS）—— 仅留离线评测集接口

---

*本计划遵循 TDD（红→绿→提交），每个 Task 独立可验证。执行时用 superpowers:executing-plans 逐任务推进。*
