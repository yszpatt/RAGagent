# KnowledgePilot

面向企业知识库的 RAG 问答系统（demo）。上传 PDF / DOCX / MD / TXT 文档，自动完成解析、切块、向量化入库（bge-m3 embedding + pgvector），回答问题时先做权限过滤的向量检索 + bge-reranker-v2-m3 精排，再按置信度给出带页码引用的答案；低相关时触发 No-Answer 兜底，不硬编答案。文档接入走 RQ 异步任务，前端为 Next.js 聊天界面。

## 架构

```
┌────────────┐  upload   ┌───────────────────────┐  enqueue   ┌──────────────────────────┐
│  frontend  │ ────────▶ │  FastAPI (uvicorn)    │ ─────────▶ │  RQ Worker (ingestion)   │
│  Next.js   │  chat     │  app/api/v1/*         │            │  解析→切块→bge-m3→入库    │
│  :3000     │ ◀──────── │  :8000                │  status    │                          │
└────────────┘           └──────────┬────────────┘            └──────────┬───────────────┘
        /api/* 反向代理到 :8000       │                                   │
                                    ▼                                   ▼
                          ┌───────────────────────────────────────────────────┐
                          │  PostgreSQL + pgvector (:5432)                    │
                          │  documents / chunks(embedding) / document_permissions│
                          └───────────────────────────────────────────────────┘
        Redis (:6379)  ← RQ 队列
```

**问答链路**（`app/generation/graphs/query_graph.py`，LangGraph 状态机）：

```
用户提问(query, roles) → 向量检索 top-10(SQL 里按角色过滤 document_permissions)
  → bge-reranker-v2-m3 精排取前5 → 置信度 ≥ rerank_threshold?
     是 → 组装 top-5 上下文 → Ollama LLM 生成回答 + 引用[{chunk_id, page}]
     否 → No-Answer 兜底文案
```

**接入链路**（`app/ingestion/pipeline.py`，RQ 异步）：

```
上传 → RQ 队列 → worker 领取 → parsers 解析(txt/md/pdf/docx)
  → recursive_chunk 递归切块(保留页码) → bge-m3 向量化 → add_chunks 单事务批量入库
  → documents.status = completed（失败则 failed + 清理孤儿 chunk）
```

## 仓库结构

```
backend/
  app/
    api/v1/           # documents / chat / conversations 路由
    core/config.py    # 配置（DATABASE_URL / REDIS_URL / 模型名）
    ingestion/        # parsers / chunkers / pipeline / tasks(RQ)
    retrieval/        # vector_store.py（pgvector + 检索前权限过滤）
    generation/       # LangGraph query_graph + embedding/reranker/llm providers
    guardrails/       # no_answer 置信度护栏
  sql/schema.sql      # 建表 DDL（对应设计文档 §5）
  tests/              # pytest 单测 + e2e_smoke.py
  pyproject.toml      # 依赖（含 uvicorn / rq / sentence-transformers）
  Dockerfile
frontend/             # Next.js 16 + React 19 + Tailwind 4
  app/                # / 问答 · /documents 知识库 · /admin/* 看板/权限/审计（预览）
  components/         # 应用壳、聊天卷宗条目、来源案卷抽屉、上传区、UI 基础件
  lib/                # api 客户端 / demo 占位数据 / 演示模式上下文
deploy/docker-compose.yml
docs/plans/           # 设计文档与实现计划
```

## 快速开始

### 0. 前置条件

- Docker（跑 PostgreSQL + Redis）
- Python ≥ 3.11（建议 venv）
- Node.js ≥ 18（跑前端）

### 1. 启动基础设施（PostgreSQL + Redis）

```bash
docker compose -f deploy/docker-compose.yml up -d postgres redis
# 等价于：
#   docker run -d --name kp-pg    -p 5432:5432 -e POSTGRES_USER=kp -e POSTGRES_PASSWORD=kp \
#     -e POSTGRES_DB=knowledgepilot pgvector/pgvector:pg16
#   docker run -d --name kp-redis -p 6379:6379 redis:7-alpine
```

初始化数据库表结构：

```bash
docker compose exec -T postgres psql -U kp -d knowledgepilot < backend/sql/schema.sql
```

### 2. 安装后端

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -e '.[dev]'   # dev 含 pytest；生产可去掉 [dev]
```

首次使用会自动从 HuggingFace 下载模型（约 2.3GB，存于 `~/.cache/huggingface`）：

- `BAAI/bge-m3`（1024 维 embedding）
- `BAAI/bge-reranker-v2-m3`（精排）

> HF 文件传输被墙时，用 hf-mirror：`export HF_ENDPOINT=https://hf-mirror.com`；  
> 或走 ModelScope 下载后按 `snapshots/blobs/refs` 布局手动构造 HF 缓存（见下）。

```bash
# 可选：ModelScope 下载 + 构造 HF 缓存（hf.co 直连不通时的替代方案）
pip install modelscope
modelscope download --model BAAI/bge-m3
python - <<'EOF'
import hashlib, shutil
from pathlib import Path
src = Path.home()/'.cache/modelscope/models/BAAI--bge-m3/snapshots/master'
dst = Path.home()/'.cache/huggingface/hub/models--BAAI--bge-m3'
rev = '0'*40
snap = dst/'snapshots'/rev
(snap/'1_Pooling').mkdir(parents=True, exist_ok=True)
(dst/'blobs').mkdir(parents=True, exist_ok=True)
(dst/'refs').mkdir(parents=True, exist_ok=True)
for f in [p for p in src.rglob('*') if p.is_file() and 'onnx' not in p.parts and 'imgs' not in p.parts]:
    sha = hashlib.sha256(f.read_bytes()).hexdigest()
    blob = dst/'blobs'/sha
    if not blob.exists(): shutil.copy2(f, blob)
    ln = snap/f.relative_to(src); ln.parent.mkdir(parents=True, exist_ok=True)
    if ln.exists(): ln.unlink()
    ln.symlink_to(blob.relative_to(ln.parent))
(dst/'refs'/'main').write_text(rev)
EOF
```

### 3. 启动后端 API + Worker（两个进程）

> 可选 — 启动 Ollama 本地 LLM（回答生成）：`ollama pull qwen2.5:7b && ollama serve`  
> 未启动 Ollama 时，回答自动降级为检索片段回显（"根据资料：{top chunk 内容前缀}"），demo 仍可正常演示。

```bash
# 终端 1 —— API（端口 8000）
cd backend && .venv/bin/uvicorn app.main:app --port 8000

# 终端 2 —— 文档接入 worker（首次会加载 bge-m3，稍慢）
cd backend && .venv/bin/rq worker ingestion
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000，/api/* 由 next.config 反代到 :8000
```

## 演示走查

1. 打开 <http://localhost:3000/documents>，上传一份合同（txt/md/pdf/docx 均可），等待状态变为 `completed`。
   - 也可用 API：`curl -X POST http://localhost:8000/api/v1/documents/upload -F "file=@sample.txt"`
   - 轮询状态：`curl http://localhost:8000/api/v1/documents/<document_id>`
2. 回到首页，提问"违约金是多少？"——若文档含违约金条款，会返回带页码引用的答案；点击引用档号牌可打开来源案卷。
   - API：`curl -X POST http://localhost:8000/api/v1/chat -H 'Content-Type: application/json' -d '{"query":"违约金是多少？"}'`
3. 问与知识库无关的问题（如"今天天气怎么样？"）→ 触发 No-Answer 兜底文案。

> 后端未启动时，前端自动进入**演示模式**（侧栏左下角可手动开关）：问答、知识库、看板/权限/审计均使用占位数据，便于纯前端预览。

## 前端设计

「档案室」视觉体系：瓷灰底 + 蓝黑墨 + 靛蓝交互，朱砂色只用于「需核验的标注」（引用档号牌、失败状态、预览标记）。问答以卷宗条目呈现（回合编号 + 问/答眉标），引用可点击打开来源案卷抽屉。规划中功能（使用看板、权限矩阵、审计日志、引用内容接口）已提供带占位数据的预览入口，后端接口落地后按页内提示接入。

## 技术栈

| 层         | 选型                                      |
| --------- | --------------------------------------- |
| 后端框架      | FastAPI + Uvicorn                       |
| 编排        | LangGraph（问答状态机）                        |
| 异步任务      | RQ + Redis                              |
| 向量库       | PostgreSQL + pgvector（HNSW 索引）          |
| Embedding | BAAI/bge-m3（1024 维，本地）                  |
| Rerank    | BAAI/bge-reranker-v2-m3（本地）             |
| LLM       | Ollama qwen2.5:7b（回答生成，不可用时自动降级为检索片段回显） |
| 解析        | pypdf / python-docx / 内置 txt、md         |
| 切块        | 递归切块（保留页码）                              |
| 前端        | Next.js 16 + React 19 + Tailwind 4 + lucide-react |

## 测试

前置：PostgreSQL 运行中（schema 已建）、可联网或已有模型缓存。

```bash
cd backend
.venv/bin/pytest                     # 单元测试（49 个，解析/切块/入库/检索/权限/护栏/API）
.venv/bin/python tests/e2e_smoke.py  # 端到端冒烟（真实 bge-m3 + reranker）
```

`e2e_smoke.py` 会自动起 uvicorn + RQ worker、上传 txt/md 样例文档、轮询接入完成、走 chat 断言回答与引用，最后打印 PASS/FAIL 汇总并清理进程。检测到本地模型缓存时自动启用 HF 离线模式；如需强制联网下载可设 `KP_E2E_ONLINE=1`。

## 已知限制（demo 范围）

- **无鉴权**：角色在服务端写死（admin/manager/employee），demo 未实现鉴权。权限过滤逻辑在检索前 SQL 中生效，但没有登录体系。
- **无 OCR**：扫描件无法提取文本，pipeline 会标记 `failed`（预留 marker 接口）。
- **无 SSE 流式**：chat 为同步返回；前端以打字机效果呈现答案，打字为客户端动画而非真流式。
- **回答依赖本地 Ollama**：回答默认经 Ollama LLM 生成（需本地运行 Ollama + qwen2.5:7b）；Ollama 不可用时自动降级为检索片段回显（"根据资料：{top chunk 内容前缀}"），保证 demo 不中断。
- **单用户**：会话仅存于浏览器本地（localStorage），后端 conversations 路由仍为空桩、无多租户。
- **引用内容查看**：来源案卷抽屉的原文摘录仅演示模式可用；真实引用待后端 `GET /chat/{id}/citations` 接口。
- **对象存储**：文件存本地 `/tmp/kp_uploads`，未接 S3。

## 部署（Docker Compose）

`deploy/docker-compose.yml` 覆盖后端基础设施与 API/Worker 的容器化：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

- `postgres`（pgvector）、`redis` 由镜像提供；
- `api` / `worker` 基于 `backend/Dockerfile`（python:3.11-slim + `pip install .`）构建；
- `api` 容器启动后需手动执行 schema 初始化：`docker compose exec -T postgres psql -U kp -d knowledgepilot < backend/sql/schema.sql`（首次），并确认模型缓存已挂载/可下载。

**前端不打包进 Compose**：demo 阶段前端用 `npm run dev` 本地运行（3000 端口，反代到 API）。两种模式分工：**Compose 管后端基础设施**，**前端本地 dev**。如需把前端也容器化，可为其加一个基于 `node:20` 的 `next build && next start` 镜像并 `depends_on: api`。

