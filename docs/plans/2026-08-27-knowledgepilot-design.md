# KnowledgePilot（W3）技术设计文档

> 版本：v1.0 · 日期：2026-08-27 · 状态：设计阶段（未进入开发）
> 上游输入：`RAG-KnowledgePilot-Kickoff-Brief.md` + `KnowledgePilot-产品设计与规划.md`
> 本文档定义**系统架构、数据模型、API 契约、关键流程与错误处理**，作为后续开发（writing-plans → 实现）的唯一依据。

---

## 1. 设计目标与约束

### 1.1 目标
构建 production-grade 企业知识库（RAG）系统：接入混乱业务数据，支持自然语言检索与推理，输出带引用溯源、权限隔离的答案。

### 1.2 硬性约束（客户指定）
- 技术栈：Python · LangChain/LangGraph · React.js · 多 LLM（OpenAI/Claude/Gemini）· Vector DB · semantic search
- 必须支持 reranking、embeddings/chunking/retrieval/vector search
- 必须在真实混乱业务数据上稳定工作（非 demo）

### 1.3 本阶段已确认的决策
| 决策点 | 选择 |
|---|---|
| 仓库结构 | Monorepo（backend + frontend + docs + deploy） |
| 部署形态 | 本地 Docker Compose 起步，架构预留 K8s 迁移能力 |
| 文档深度 | 架构 + 数据模型 + API 契约（可照文档直接开发） |

---

## 2. 架构决策记录（ADR）

### ADR-1：向量数据库选型
| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **pgvector** | 复用 Postgres，零新增基础设施，事务一致，元数据与向量同库过滤 | 大规模（>1M chunk）时 ANN 性能需调优 | ✅ **采用（起步）** |
| Qdrant | 专用向量检索，性能强，过滤丰富 | 新增一个服务，运维成本 | 预留（chunk>1M 或托管需求时迁移） |
| Pinecone | 全托管，零运维 | 数据驻留受限，成本高 | 不采用 |

**决策**：pgvector 起步，通过 **VectorStore 抽象接口**隔离实现，迁移时不改业务层。

### ADR-2：异步 ingestion 任务处理
| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **Redis + RQ** | 轻量、Python 原生、复用已有 Redis | 功能弱于 Celery（无复杂路由） | ✅ **采用** |
| Celery | 成熟、生态全、支持复杂任务流 | 重、引入 broker 复杂配置 | 备选 |
| FastAPI BackgroundTasks | 零依赖 | 进程内执行，重启即丢，不可扩展 | 不采用 |

**决策**：Redis + RQ 处理耗时任务（文档解析/OCR/切块/embedding），任务状态落库，前端轮询进度。

### ADR-3：LLM / Embedding / Rerank 抽象
| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **Provider Interface + 工厂** | 多模型可切换，成本/质量可调，便于评测 | 需自定义抽象层 | ✅ **采用** |
| 直接 LangChain 原生 | 开发快 | 绑定具体 provider，切换成本高 | 不采用（LangChain 仅作 primitive 层） |

**决策**：定义 `LLMProvider` / `EmbeddingProvider` / `RerankerProvider` 三个接口，工厂按配置实例化；底层可调用 LangChain/LangGraph 原语。

### ADR-4：LangGraph 编排粒度
| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **双图**：ingestion graph + query graph | 职责清晰，接入与问答解耦 | 需维护两个图 | ✅ **采用** |
| 单图全流程 | 简单 | ingestion 与 query 生命周期完全不同，强行耦合 | 不采用 |

**决策**：两条独立 LangGraph 图——`IngestionGraph`（接入）与 `QueryGraph`（问答），共享状态定义。

### ADR-5：权限过滤位置
| 方案 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **检索前过滤（SQL 层 WHERE）** | 越权数据根本不参与召回，零泄漏 | 需权限字段入库 + 查询拼接 | ✅ **采用** |
| 检索后裁剪 | 实现简单 | 召回结果先拿到再裁，存在泄漏窗口 | 不采用 |

**决策**：权限范围随 chunk 入库存为元数据列，检索时在向量查询的 WHERE 子句强制过滤。

---

## 3. Monorepo 目录结构

```
RAGAgent/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── core/                   # 配置、日志、依赖注入、异常
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── exceptions.py
│   │   ├── api/                    # 路由层（薄，只做参数校验与响应包装）
│   │   │   └── v1/
│   │   │       ├── documents.py
│   │   │       ├── chat.py
│   │   │       ├── conversations.py
│   │   │       └── admin.py
│   │   ├── domain/                 # 领域模型（dataclass / pydantic）
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   └── message.py
│   │   ├── ingestion/              # 接入管线
│   │   │   ├── connectors/         # 数据源连接器
│   │   │   ├── parsers/            # PDF/OCR/Excel/DOCX 解析
│   │   │   ├── chunkers/           # 语义 + 递归切块
│   │   │   └── embedders/          # 向量化
│   │   ├── retrieval/              # 检索 + rerank
│   │   │   ├── vector_store.py     # VectorStore 抽象 + pgvector 实现
│   │   │   ├── retriever.py
│   │   │   └── reranker.py
│   │   ├── generation/             # LangGraph 编排 + LLM
│   │   │   ├── graphs/
│   │   │   │   ├── ingestion_graph.py
│   │   │   │   └── query_graph.py
│   │   │   └── providers/          # LLM/Embedding/Rerank provider
│   │   ├── guardrails/             # No-Answer、引用校验
│   │   └── services/               # 业务服务层（编排领域逻辑）
│   ├── alembic/                    # DB 迁移
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                       # React (Next.js)
│   ├── app/
│   ├── components/
│   └── Dockerfile
├── deploy/
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml     # 预留
├── docs/
│   └── plans/                      # 本文档所在
└── README.md
```

---

## 4. 系统架构

### 4.1 数据流总览

**接入链路（异步）**：
```
上传文档 → 存储(对象存储/本地) → 创建 IngestionJob(状态=pending)
        → RQ Worker 领取 → 解析(OCR/表格) → 切块 → Embedding → 写入 pgvector(+权限元数据)
        → 更新 Job 状态=completed / failed
```

**问答链路（同步 + SSE 流式）**：
```
用户提问 → 权限上下文注入 → 向量检索 top-k(WHERE 权限过滤) → Rerank
        → 上下文组装 → LLM 生成(带引用) → 置信度判定
        → 高置信: 返回答案 + 引用   /   低置信: No-Answer 兜底
        → 写审计日志
```

### 4.2 模块职责

| 模块 | 职责 | 依赖 |
|---|---|---|
| `ingestion.connectors` | 数据源接入（本地文件/URL，预留 SaaS） | — |
| `ingestion.parsers` | 多格式解析，含 OCR、表格提取 | unstructured.io / marker |
| `ingestion.chunkers` | 语义 + 递归切块，保留页码/节元数据 | — |
| `ingestion.embedders` | 文本向量化 | EmbeddingProvider |
| `retrieval.vector_store` | 向量 + 元数据存储，权限过滤 | pgvector |
| `retrieval.retriever` | top-k 召回 | vector_store |
| `retrieval.reranker` | 精排 | Cohere / bge-reranker |
| `generation.graphs` | LangGraph 编排 | LLMProvider |
| `guardrails` | No-Answer 阈值、引用有效性 | — |
| `services` | 业务编排（上传、问答、权限、审计） | 各模块 |

---

## 5. 数据模型（PostgreSQL + pgvector）

### 5.1 表结构

```sql
-- 工作区（复用 Common Platform 概念，本系统内实现）
CREATE TABLE workspaces (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 用户（对接外部 Auth，此处仅存最小映射）
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id   VARCHAR(255) UNIQUE,      -- SSO / 外部系统 ID
    role          VARCHAR(32) NOT NULL,     -- admin | manager | employee
    workspace_id  UUID REFERENCES workspaces(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 文档
CREATE TABLE documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id),
    title         VARCHAR(512) NOT NULL,
    source_type   VARCHAR(32) NOT NULL,     -- pdf | docx | xlsx | pptx | html | md | txt
    storage_path  VARCHAR(1024) NOT NULL,   -- 原始文件位置
    status        VARCHAR(32) NOT NULL,     -- pending | processing | completed | failed
    error_message TEXT,
    created_by    UUID REFERENCES users(id),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 权限（文档级 ACL）
CREATE TABLE document_permissions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    role          VARCHAR(32) NOT NULL,     -- admin | manager | employee
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(document_id, role)
);

-- 文本块（含向量）
CREATE TABLE chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content       TEXT NOT NULL,
    chunk_index   INT NOT NULL,
    page_number   INT,                       -- 页码（PDF 溯源）
    section_title VARCHAR(512),              -- 节标题
    token_count   INT NOT NULL,
    embedding     vector(1536),              -- 维度随 embedding 模型可调
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 向量索引（HNSW）
CREATE INDEX idx_chunks_embedding ON chunks
    USING hnsw (embedding vector_cosine_ops);

-- 块级权限物化（检索时 WHERE 过滤的关键列）
-- 通过 document_permissions 关联文档角色，查询时 JOIN 过滤

-- 会话
CREATE TABLE conversations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id),
    workspace_id  UUID NOT NULL REFERENCES workspaces(id),
    title         VARCHAR(512),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 消息
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(16) NOT NULL,    -- user | assistant
    content         TEXT NOT NULL,
    citations       JSONB,                   -- [{chunk_id, document_id, page, section}]
    no_answer       BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 接入任务（异步状态）
CREATE TABLE ingestion_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status        VARCHAR(32) NOT NULL,      -- pending | running | completed | failed
    progress      INT DEFAULT 0,             -- 0-100
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ
);

-- 审计日志
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id),
    action          VARCHAR(64) NOT NULL,    -- query | upload | permission_change | ...
    query_text      TEXT,
    retrieved_chunk_ids UUID[],
    response_ref    UUID,                    -- 关联 messages.id
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_logs_user_time ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_logs_ws_time ON audit_logs(workspace_id, created_at DESC);
```

### 5.2 权限过滤实现

检索时，通过 JOIN `document_permissions` 生成用户可见文档集合，在向量查询 WHERE 子句中过滤：

```sql
SELECT c.id, c.content, c.page_number, c.section_title, c.embedding <=> :query_vec AS distance
FROM chunks c
JOIN documents d ON c.document_id = d.id
JOIN document_permissions dp ON d.id = dp.document_id
WHERE dp.role IN (:user_roles)          -- 权限过滤（检索前）
  AND d.workspace_id = :workspace_id
ORDER BY distance ASC
LIMIT :top_k;
```

**关键点**：`dp.role IN (:user_roles)` 在检索前执行，越权 chunk 根本不进入召回集。

---

## 6. API 契约（REST）

统一前缀 `/api/v1`，认证走 `Authorization: Bearer <token>`。

### 6.1 文档管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/documents/upload` | 上传文档（multipart），返回 document_id + job_id |
| GET | `/documents` | 列出工作区文档（含状态、权限） |
| GET | `/documents/{id}` | 文档详情 |
| GET | `/documents/{id}/status` | 解析/接入进度 |
| DELETE | `/documents/{id}` | 删除文档（级联删 chunk + 权限） |

**POST /documents/upload**
```json
// 请求：multipart/form-data（file 字段 + role_visibility 字段）
// 响应 202 Accepted：
{
  "document_id": "uuid",
  "job_id": "uuid",
  "status": "pending"
}
```

### 6.2 问答

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | 发起问答（SSE 流式返回） |
| GET | `/chat/{message_id}/citations` | 获取回答引用的来源详情 |

**POST /chat** — 请求：
```json
{
  "conversation_id": "uuid | null",
  "query": "我们去年签的供应商合同里违约金条款是什么？"
}
```

**POST /chat** — SSE 响应事件流：
```
event: token        data: {"content": "根据..."}          # 增量 token
event: citation     data: {"chunk_id": "...", "document_id": "...", "page": 3, "section": "第4条"}
event: done         data: {"message_id": "uuid"}
event: no_answer    data: {"reason": "low_relevance"}       # 低置信兜底
```

### 6.3 会话管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/conversations` | 列出当前用户会话 |
| GET | `/conversations/{id}/messages` | 会话消息历史 |

### 6.4 管理端（Admin 角色）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/admin/documents/{id}/permissions` | 设置文档角色可见性 |
| GET | `/admin/audit-logs` | 查询审计日志（分页 + 过滤） |
| GET | `/admin/metrics` | 使用指标（问答数/采纳率/无答案率） |

### 6.5 统一响应与错误

```json
// 成功：
{ "data": ..., "meta": { "page": 1, "total": 100 } }

// 错误：
{
  "error": {
    "code": "PERMISSION_DENIED",       // 机器可读码
    "message": "无权访问该文档",         // 人可读信息
    "details": { ... }
  }
}
```

**错误码表**：
| code | HTTP | 场景 |
|---|---|---|
| `INVALID_ARGUMENT` | 400 | 参数校验失败 |
| `AUTHENTICATION_REQUIRED` | 401 | 未认证 |
| `PERMISSION_DENIED` | 403 | 越权访问 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `INGESTION_FAILED` | 422 | 文档解析失败 |
| `LLM_UNAVAILABLE` | 503 | LLM 服务不可用 |
| `RATE_LIMITED` | 429 | 限流 |

---

## 7. 关键流程细节

### 7.1 查询流程（LangGraph QueryGraph 状态机）

```
START
  → validate_query          # 校验 + 权限上下文注入
  → retrieve                # 向量检索 top-k（权限过滤）
  → rerank                  # 精排 top-n
  → assemble_context        # 组装带引用上下文
  → generate                # LLM 生成
  → evaluate_confidence     # 置信度判定（阈值可配置）
  → [高置信] answer         # 返回答案 + 引用
  → [低置信] no_answer      # 兜底
END
```

### 7.2 无答案兜底逻辑

判定规则（任一命中即触发兜底）：
- Rerank 后 top-1 分数 < `rerank_threshold`（默认 0.3）
- LLM 输出判定为"无法回答"（prompt 内指令 + 输出解析）
- 检索结果为空

兜底输出固定文案："未找到相关信息，请尝试换个问法。" —— **绝不编造**。

### 7.3 引用溯源

- Chunk 携带 `page_number` + `section_title` 元数据
- LLM 生成时要求按 `[1][2]` 格式标注引用
- 后处理将 `[n]` 映射到具体 chunk → 前端渲染为可点击链接，跳转到源文件页/节

### 7.4 重试与容错

| 场景 | 策略 |
|---|---|
| LLM 调用失败 | 指数退避重试 3 次，仍失败返回 `LLM_UNAVAILABLE` |
| Rerank 服务失败 | 降级为原始 top-k（记录 warning 日志） |
| Ingestion 解析失败 | 标记 `failed` + error_message，允许单条重传 |
| 向量检索超时 | 500ms 超时，降级为 BM25（预留混合检索） |

---

## 8. 错误处理与可观测性

- **结构化日志**：JSON 格式，含 `request_id` 贯穿全链路（trace_id）
- **审计**：query / upload / permission_change 三类关键动作全记录
- **健康检查**：`GET /health`（liveness）+ `GET /health/ready`（依赖就绪）
- **指标暴露**：Prometheus 端点（`/metrics`），埋点 p95 时延、无答案率、失败率

---

## 9. 测试策略

| 层 | 内容 | 工具 |
|---|---|---|
| 单元测试 | chunker/parser 边界、权限过滤 SQL | pytest |
| 集成测试 | ingestion → retrieval → generation 端到端 | pytest + testcontainers(pgvector) |
| 检索质量评测 | Recall@K、MRR、Rerank Lift | 离线评测集（M2 建立） |
| 越权测试 | 员工角色无法检索 manager 文档（0 泄漏断言） | pytest 专项用例 |
| 生成质量评测 | Faithfulness / Relevance | RAGAS + LLM-as-judge |

---

## 10. 部署架构（Compose，预留云迁移）

```
docker-compose.yml:
├── api          # FastAPI (uvicorn)
├── worker       # RQ Worker（ingestion 异步任务）
├── frontend     # Next.js
├── postgres     # PostgreSQL + pgvector 扩展
├── redis        # 缓存 + RQ 队列
└── (可选) nginx # 反向代理 + 静态资源
```

**云迁移预留**：通过 VectorStore / StorageBackend / LLMProvider 抽象接口 + 环境变量注入，迁移 K8s 时替换为托管服务（RDS + Qdrant + S3），不改业务代码。

---

## 11. 安全与合规

- 密钥走环境变量 / Secret 管理，绝不硬编码
- 用户输入与 LLM 输出做转义（防 XSS / prompt injection）
- 文档数据加密存储（at-rest）+ TLS 传输（in-transit）
- 越权访问 = 0 容忍，审计日志可追溯
- 默认安全：新上传文档仅 Admin 可见

---

## 12. 待确认事项（阻塞开发前）

| # | 事项 | 影响 |
|---|---|---|
| 1 | 数据规模与格式（决定 pgvector 是否起步即需优化） | ADR-1 |
| 2 | Embedding 维度（text-embedding-3 默认 1536，可调） | 表结构 |
| 3 | LLM/Rerank provider 最终选型与成本上限 | ADR-3 |
| 4 | 是否对接外部 SSO | users 表 external_id |
| 5 | 对象存储选型（本地 / S3 / 云存储） | documents.storage_path |

---

*本文档为设计阶段产出，未包含任何实现代码；进入开发前需先完成 §12 待确认事项，并用 writing-plans 拆解为可执行任务。*
