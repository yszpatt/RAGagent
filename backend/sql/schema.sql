-- KnowledgePilot 数据库 Schema（demo 版）
-- 用法: psql -h localhost -U kp -d knowledgepilot -f backend/sql/schema.sql
-- 说明: 对应设计文档 §5 数据模型；bge-m3 为 1024 维向量。
-- 注意: 本文件为 schema 权威来源，修改 models.py 需同步更新（反之亦然）。

CREATE EXTENSION IF NOT EXISTS vector;

-- 工作区（demo：pipeline 自动创建"默认工作区"）
CREATE TABLE IF NOT EXISTS workspaces (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 用户（对接外部 Auth，此处仅存最小映射；demo 无鉴权，角色走 chat 请求体）
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   VARCHAR(255) UNIQUE,
    role          VARCHAR(32) NOT NULL,     -- admin | manager | employee
    workspace_id  UUID REFERENCES workspaces(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 文档
CREATE TABLE IF NOT EXISTS documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id),
    title         VARCHAR(512) NOT NULL,
    source_type   VARCHAR(32) NOT NULL,     -- pdf | docx | md | txt ...
    storage_path  VARCHAR(1024) NOT NULL,
    status        VARCHAR(32) NOT NULL,     -- pending | processing | completed | failed
    error_message TEXT,
    created_by    UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 权限（文档级 ACL，检索前过滤）
CREATE TABLE IF NOT EXISTS document_permissions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role          VARCHAR(32) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, role)
);

-- 文本块（含向量，bge-m3 1024 维）
CREATE TABLE IF NOT EXISTS chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    chunk_index   INT NOT NULL,
    page_number   INT,
    section_title VARCHAR(512),
    token_count   INT NOT NULL,
    embedding     vector(1024) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 向量索引（demo 数据量小可省略；数据量大时启用）
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops);

-- 会话
CREATE TABLE IF NOT EXISTS conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id),
    title         VARCHAR(512),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 消息
CREATE TABLE IF NOT EXISTS messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,    -- user | assistant
    content         TEXT NOT NULL,
    citations       JSONB,
    no_answer       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 接入任务（异步状态）
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status        VARCHAR(32) NOT NULL,      -- pending | running | completed | failed
    progress      INT DEFAULT 0,
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);

-- 审计日志
CREATE TABLE IF NOT EXISTS audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id),
    action          VARCHAR(64) NOT NULL,    -- query | upload | permission_change | ...
    query_text      TEXT,
    retrieved_chunk_ids UUID[],
    response_ref    UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time ON audit_logs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_ws_time ON audit_logs(workspace_id, created_at DESC);
