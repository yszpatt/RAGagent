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
用户提问(query, roles)
  → 向量检索 top-20 → 近重复剔除 → 取前 10（SQL 里按角色过滤 document_permissions）
  → bge-reranker-v2-m3 精排取前 5
  → Tier1 门控：最高余弦相似度 ≥ answer_gate(0.45)?
       否 → No-Answer 兜底文案（不消耗 LLM）
       是 → 组装 top-5 上下文 → LLM 生成回答 + 引用[{chunk_id, page}]
          → Tier3 终审：LLM 输出 __NO_ANSWER__ ? → 是则转 No-Answer
```

三级判定的职责分工见下方 [No-Answer 三级判定](#no-answer-三级判定)。

**接入链路**（`app/ingestion/pipeline.py`，RQ 异步）：

```
上传 → 落 documents 行(status=pending) + 按 sha256 去重
  → RQ 队列 → worker 领取 → parsers 解析(txt/md/pdf/docx)
  → 条款感知切块(按 条/章/节 切，标题回填进 section_title，保留页码)
  → bge-m3 批量向量化 → add_chunks 单事务入库
  → documents.status = completed（失败则 failed + 清理孤儿 chunk）
```

## 仓库结构

```
backend/
  app/
    api/v1/           # documents / chat / conversations / admin 路由
    services/         # audit（审计日志写入）/ context（请求上下文）
    core/config.py    # 配置（DATABASE_URL / REDIS_URL / 模型名 / LLM 接入 / 阈值）
    ingestion/        # parsers / chunkers / pipeline / tasks(RQ)
      chunkers/
        clause_aware.py  # 条款感知切块（中文企业文档，按 条/章/节 切 + 标题回填）
        recursive.py     # 通用递归切块（回退 / 非中文语料）
    retrieval/        # vector_store.py（pgvector + 检索前权限过滤 + 引用详情）
      dedup.py        # 检索结果近重复剔除（3-gram 重叠系数）
    generation/       # LangGraph query_graph + embedding/reranker/llm providers
    guardrails/       # no_answer 置信度护栏
  sql/schema.sql      # 建表 DDL（对应设计文档 §5）
  tests/              # pytest 单测 + e2e_smoke.py
  pyproject.toml      # 依赖（含 uvicorn / rq / sentence-transformers）
  Dockerfile
frontend/             # Next.js 16 + React 19 + Tailwind 4
  app/                # / 问答 · /documents 知识库 · /admin/* 看板/权限/审计（已接 /admin 接口）
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

### 3. 配置 LLM（本地 / 局域网 / 第三方，任选其一）

回答生成走 **OpenAI Chat Completions 兼容协议**，一套代码覆盖所有部署形态。
通过 `backend/.env` 或环境变量配置（改完需重启 API）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` 走原生 `/api/generate`；`openai_compat` 走 `/v1/chat/completions` |
| `LLM_BASE_URL` | 空 | 留空则回落到 `OLLAMA_BASE_URL`。兼容模式下会自动补 `/v1` 后缀 |
| `LLM_MODEL` | `qwen2.5:7b` | 模型名，按目标服务实际可拉取的名称填 |
| `LLM_API_KEY` | 空 | Ollama 不需要真实 key，填任意占位值即可 |
| `LLM_TIMEOUT` | `120` | 超时秒数；局域网/公网建议调大 |
| `LLM_TEMPERATURE` | `0.0` | **不要留空**：默认温度下 Tier3 判定会随机翻转，详见「温度必须显式置 0」 |

四种典型场景：

```bash
# ① 本机 Ollama（默认，不需要额外配置）
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434

# ② Ollama 装在局域网另一台机器上（用 openai_compat 走 Ollama 自带的兼容端点）
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://192.168.1.50:11434/v1
LLM_MODEL=qwen2.5:7b
LLM_API_KEY=ollama          # 占位值，Ollama 不校验
# 记得在该机器上设置 OLLAMA_HOST=0.0.0.0，否则只监听 127.0.0.1

# ③ vLLM / Xinference / LocalAI 等自建推理服务
LLM_PROVIDER=openai_compat
LLM_BASE_URL=http://192.168.1.60:8000/v1
LLM_MODEL=Qwen2.5-7B-Instruct
LLM_API_KEY=<你的 key 或占位值>

# ④ 第三方 API（DeepSeek / Moonshot / 通义千问兼容模式 / SiliconFlow / OpenAI）
LLM_PROVIDER=openai_compat
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
LLM_API_KEY=sk-xxxx
```

> LLM 不可用时，回答自动降级为检索片段回显（"根据资料：{top chunk 内容前缀}"），
> demo 仍可正常演示，但 **Tier3 终审会被跳过**（详见下方三级判定）。

**排查清单**（按本次实测踩到的顺序）：

| 现象 | 原因 | 处理 |
|---|---|---|
| `does not support chat` | 填了 **embedding 模型**（如 `bge-m3`）。它只能出向量，不能对话 | 生成必须用 chat 类模型。用 `curl http://host:11434/api/tags` 看该机器上到底有哪些模型，别照抄 embedding 的名字 |
| `Connection refused` | 目标机器只监听 127.0.0.1 | 在那台机器上设 `OLLAMA_HOST=0.0.0.0` 后重启 Ollama |
| 首次提问特别慢（冷启动 26s，之后 3~9s） | 大模型从磁盘加载；Ollama 默认空闲 5 分钟卸载 | 调大 `LLM_TIMEOUT`（30B 模型建议 180），或设 `OLLAMA_KEEP_ALIVE=-1` 常驻显存 |
| 同样的问题两次答案不同 | 未显式下发 `temperature` | 设 `LLM_TEMPERATURE=0`（已是默认值，但别被覆盖掉） |

> 配置文件位置注意：`.env` 需放在 **`backend/` 目录**下。pydantic 的 `env_file`
> 是相对**当前工作目录**解析的，而服务从 `backend/` 启动 —— 放在仓库根目录的
> `.env.example` 只是模板，不会被读取。

### 4. 启动后端 API + Worker（两个进程）

```bash
# 终端 1 —— API（端口 8000）
cd backend && .venv/bin/uvicorn app.main:app --port 8000

# 终端 2 —— 文档接入 worker（首次会加载 bge-m3，稍慢）
cd backend && .venv/bin/rq worker ingestion
```

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000，/api/* 由 next.config 反代到 :8000
```

## 关键设计

> 以下结论均来自对真实语料的实测，复现脚本见 `backend/tests/bench/` 与
> `docs/plans/2026-08-29-optimization-plan.md`。

### No-Answer 三级判定

「什么时候该拒答」是 RAG 最容易做错的地方。本项目的做法是把**三种信号拆开，
各管一件事**：

| 层级 | 用什么信号 | 回答什么问题 | 关键理由 |
|---|---|---|---|
| Tier1 门控 | bge-m3 余弦相似度 | 语料里**有没有**能答的东西 | 绝对量纲稳定，适合做廉价预筛 |
| Tier2 精排 | bge-reranker-v2-m3 | 用**哪几段** | 只排序，**不参与判定** |
| Tier3 终审 | LLM 读上下文 | 这些段落**是否真的**回答了问题 | 基于内容，不受语料规模影响 |

关键实测结论：

1. **Reranker 的绝对分数不能用来判拒答。** 域内最低 0.0184 竟然低于域外最高
   0.0280 —— 两者分布严重重叠。原实现用 `rerank_threshold=0.3` 做门控，
   实测**误杀了 40%（6/15）的正确答案**；改由 embedding 余弦门控后 F1 从
   0.75 升到 1.00。Reranker 擅长排序，不擅长定阈值，这是它的训练目标决定的。
2. **阈值会随语料规模漂移。** 语料从 15 篇涨到 35 篇时，域外查询的最高相似度
   从 0.5256 漂到 0.5996。因此 Tier1 刻意按**召回优先**设定（当前 0.45，
   对实测域内最低值 0.5438 留 0.094 余量），精度问题交给 Tier3 兜底 ——
   误杀的代价（本该答对的直接拒答，用户无解）远大于放过的代价
   （多跑一次 LLM，由 Tier3 按内容判回拒答）。
3. **Tier3 是形似干扰项的唯一解。** 像「劳动合同法规定的试用期上限是多少」
   这种问题，检索到的都是本公司制度段落，相似度高达 0.64（远高于阈值），
   只有读懂内容才判断得出「这不是在问我们公司」。这类问题 Tier1 结构上无解。

相关配置：`ANSWER_GATE` / `ANSWER_GATE_ENABLED` / `LLM_FINAL_CHECK` /
`RERANK_THRESHOLD`（兼容开关）。**换语料后请重新标定**：

```bash
cd backend && .venv/bin/python tests/bench/calibrate_noanswer.py
```

端到端评测（44 条标注集，需 API + LLM 在线）：

```bash
cd backend && .venv/bin/python scripts/eval_no_answer.py          # 主指标 + 边界
.venv/bin/python scripts/eval_no_answer.py --only out -v          # 只看域外误放行
```

### Tier3 的两类错配（实测 44 条）

Tier3 的拒答错误不是单一原因，而是两种**性质相反**的错配，必须分开写规则：

| | 错配类型 | 例子 | 正确处理 |
|---|---|---|---|
| 甲类 | **术语错配**（口语 vs 书面语） | 问「这合同能**作废**吗」，资料写「**解除**」 | 映射后**回答** |
| 乙类 | **作用域错配**（内部规定 vs 外部通用） | 问「**一般公司**的违约金是怎么算的」，资料只有本合同约定 | **拒答** |

只放宽映射（试图修甲类）会让乙类漏出去，实测**净零**：域内 +1、域外 −1。

| SYSTEM_PROMPT | 主指标 | 域内 | 域外误放行 |
|---|---|---|---|
| 原始版 | 41/42 | 22/23 | 0 |
| 只加术语映射（v2） | 41/42 | 23/23 | **1** ❌ |
| 两类错配都写（v3，当前） | **42/42** | **23/23** | **0** ✅ |

> 口径说明：42 = 44 条标注集剔除 2 条 `BOUNDARY`；其中 5 条首版误标的查询已按
> 语料查证改判为拒答（详见 `scripts/eval_no_answer.py` 文件头）。三个变体用同一
> 套标注、同一批真实检索上下文对比，否则数字不可比。

因此提示词里甲类允许「一步直接推理」但禁止跨片段拼装，乙类则列出作用域越界
信号词（`一般` / `通常` / `劳动法` / `民法典` / `行业标准` / `行情` …），
命中即拒答 —— 拿本公司规定充当通用答案是越权编造，比拒答危险得多。

### 温度必须显式置 0

这是实测中代价最小、却最容易被忽略的一处修复。不传 `temperature` 时
Ollama 取默认 ≈0.8，同一条查询**重复 5 次会出现 1~2 次判定翻转**：

| 查询 | 默认温度 ×5 | `temperature=0` ×5 |
|---|---|---|
| 年假没休完会怎样 | 拒答/拒答/拒答/**回答**/拒答 | 拒答 ×5 |
| 账号密码忘了找谁 | 拒答/**回答**/**回答**/拒答/拒答 | 拒答 ×5 |

域外成绩因此在 17/19 ~ 19/19 之间随机波动。知识库里「同一个问题两次问出不同
结论」是不可接受的 —— 用户会因此对系统整体失去信任。置 0 后**连续两轮 44 条
评测结果逐条一致**。

配置：`LLM_TEMPERATURE`（默认 `0.0`，两个 provider 都会显式下发）。

### 条款感知切块

中文企业文档的语义单元不是句子，而是**条款** —— 一条就是一个自足的事实单元
（主体 + 条件 + 后果）。通用递归切块按字符数硬切，在中文语料上会造成两类伤害，
均为实测：

| 问题 | 实测现象 |
|---|---|
| 整篇塌成一块 | 477 字合同 < `chunk_size` 500，8 个条款共处一块。任意问题都命中同一块，top1-top2 相似度间隙中位数仅 **0.0015**，30 条查询里 19 条几乎并列 —— 检索完全丧失区分度，「打官司去哪儿解决」的 top1 甚至落到运维文档的服务器 IP 段落 |
| 边界切断词语 | 切出「司商业秘密，不得向第三方泄露…」，「员」字残留在上一块，污染向量语义与引用展示 |

条款感知切块（`app/ingestion/chunkers/clause_aware.py`）的做法：

- 以 `第X条` / `第X章` / `一、` / `（一）` / `1.2` / Markdown `#` 为**一等边界**，
  短条款原样成块，**不做跨条款切分**；
- 标题回填进 `section_title` 并拼在内容开头，使「打官司去哪儿解决」能直接
  匹配「第十二条 争议解决」，而不只依赖正文字面重合；
- **重叠只在条款内部生效，绝不跨条款** —— 跨条款重叠会把上一条的语义带进下一条，
  恰好抵消掉按条切分的收益；
- 无标题的引导段（文档名、缔约方）并入其后的第一个条款块，不单独成块。

效果（同一批 44 条查询）：

| 指标 | 通用递归切块 | 条款感知切块 |
|---|---|---|
| 块数（4 篇文档） | 9 | 25 |
| top1-top2 间隙中位数 | 0.0015 | **0.0541**（36×） |
| 间隙 < 0.01 的查询占比 | 19/30 | **4/30** |
| 域内相似度中位数 | 0.5824 | 0.6266 |
| Tier1 误杀数 | 11/30 | **0/30** |

配置：`CHUNKER`（`clause_aware` / `recursive`）、`CHUNK_SIZE`、`CHUNK_OVERLAP`、
`CHUNK_MIN_SIZE`。**切块策略变更后需重建索引**：重新上传时带 `force=true`
（会覆盖重建同一份文档，而不是新增副本）。

### 双层去重

重复块会挤占 top-k 名额，直接压低准确度。实测语料里 7 篇文档只有 4 篇是不同
内容，9 个块中 4 个冗余 —— top_k=5 时实际多样性只剩 3。

- **入库侧（精确）**：按原始文件 sha256 去重，`(workspace_id, content_hash)`
  唯一索引。重复上传返回 409 并附带已存在文档的信息
  （实测：同一份合同曾被上传 3 次）。
- **检索侧（近似）**：3-gram **重叠系数** `|A∩B|/min(|A|,|B|) >= 0.90` 时只保留
  排在最前的那个。用重叠系数而非 Jaccard，是因为去重要回答的是
  「这块是否已被保留的某块覆盖」，属于不对称问题；Jaccard 惩罚长度差，
  实测 30 字与其 35 字扩写版只有 0.794，会漏判真正的近重复。
  去重在 **rerank 之前**执行 —— 若等到 rerank 截到 top5 再去重，
  重复项早已挤掉本可入选的其他块，多样性无法挽回。

配置：`DEDUP_ENABLED` / `DEDUP_THRESHOLD`。

## API 接口

后端 Swagger：`http://localhost:8000/docs`（前端 `/api/*` 由 Next.js 反代到该端口）。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/documents/upload` | 上传文档；`role_visibility` 表单字段指定可见角色，**JSON 数组字符串**（如 `["admin","manager"]`，缺省=全角色开放），返回 `document_id` / `job_id` / `content_hash`。内容重复时返回 **409** 并附带已存在文档的信息；带 `force=true` 则覆盖重建同一份文档（不新增副本） |
| GET | `/api/v1/documents` | 文档列表（含接入状态） |
| GET | `/api/v1/documents/{id}` | 查询单个文档接入状态（pending / completed / failed） |
| DELETE | `/api/v1/documents/{id}` | 删除文档 |
| POST | `/api/v1/documents/{id}/reingest` | 重新接入（重新解析 + 向量化） |
| PUT | `/api/v1/documents/{id}/permissions` | 设置角色可见范围（`roles` 数组，admin 始终保留） |
| POST | `/api/v1/chat` | 提问；返回带引用的答案（含原文摘录/页码/节标题），低相关时 `no_answer=true` |
| GET | `/api/v1/conversations` | 会话列表 |
| GET | `/api/v1/conversations/{id}/messages` | 会话消息历史（citations 为富化后的 JSONB） |
| GET | `/api/v1/admin/audit-logs` | 审计日志，支持 `action` / `limit` / `offset` 过滤分页 |
| GET | `/api/v1/admin/metrics` | 使用指标（文档状态分布、No-Answer 率、引用率） |
| GET | `/health` | 健康检查 |

> 引用富化在 `POST /chat` 内完成（`_enrich_citations` 按 chunk id 批量取详情），前端无需再调单独的 citations 接口。
> 管理端接口（`admin/*`）demo 阶段无鉴权，生产环境接入前需补 SSO。

## 演示走查

1. 打开 <http://localhost:3000/documents>，上传一份合同（txt/md/pdf/docx 均可），等待状态变为 `completed`。
   - 也可用 API：`curl -X POST http://localhost:8000/api/v1/documents/upload -F "file=@sample.txt"`
   - 轮询状态：`curl http://localhost:8000/api/v1/documents/<document_id>`
2. 回到首页，提问"违约金是多少？"——若文档含违约金条款，会返回带页码引用的答案；点击引用档号牌可打开来源案卷。
   - API：`curl -X POST http://localhost:8000/api/v1/chat -H 'Content-Type: application/json' -d '{"query":"违约金是多少？"}'`
3. 问与知识库无关的问题（如"今天天气怎么样？"）→ 触发 No-Answer 兜底文案。

> 后端未启动时，前端自动进入**演示模式**（侧栏左下角可手动开关）：问答、知识库、看板/权限/审计均使用占位数据，便于纯前端预览。可在 `/admin/settings` 调整主题（含暗黑模式）、界面语言、动效与演示身份。

## 前端设计

「档案室」视觉体系：瓷灰底 + 蓝黑墨 + 靛蓝交互，朱砂色只用于「需核验的标注」（引用档号牌、失败状态、预览标记）。问答以卷宗条目呈现（回合编号 + 问/答眉标），引用可点击打开来源案卷抽屉，摘录/页码/节标题由 `POST /chat` 返回的富化 citations 提供。

`/admin/*` 三个页面（使用看板、权限矩阵、审计日志）已接入后端 `/api/v1/admin/*` 真实接口；后端不可用时自动回落到**演示模式**占位数据。

### 近期前端能力

以下能力均在 demo 阶段完成，均为纯前端（偏好存浏览器 localStorage，不触后端）：

- **暗黑模式**：「深夜书房」深色主题（瓷灰底 `#141920` / 月白字 `#e4e9f1`），通过 Tailwind v4 `@theme` CSS 变量换肤，无刷新切换；通过 `prefers-color-scheme` 自动识别，可手动覆盖。
- **设置页**（`/admin/settings`，挂在管理下）：分「外观 / 语言与动效 / 当前身份（演示）/ 本地数据 / 关于」五区，可配置主题、界面语言、动画开关、演示身份，并支持清除本地会话记录与恢复默认偏好。
- **当前用户演示身份**：侧栏底部展示头像 + 姓名 + 角色徽章（admin / manager / employee，可切换）；**仅前端展示，真实权限以后端数据为准**。
- **中英双语（i18n）**：导航、侧栏、设置页、聊天面板（会话列表 / 输入区 / 欢迎语 / 引用提示）等框架文案已接入 `lib/prefs.tsx` 双语词典（`t(key)` 支持 `{n}` 插值）。内容数据（会话标题、演示问答、品牌字「知」）按设计不翻译。
- **聊天输入交互**：`Enter` 发送、`Shift+Enter` 换行（与多数 IM 一致）。
- **AppShell 滚动约束**：根容器 `h-screen overflow-hidden`，聊天区与历史列表各自独立滚动，历史会话很多时新对话面板不再错位、底部项不再被裁切。
- **大文件上传**：dev 代理请求体上限 10MB → 50MB，修复大 PDF 上传 `server error`。

## 技术栈

| 层         | 选型                                      |
| --------- | --------------------------------------- |
| 后端框架      | FastAPI + Uvicorn                       |
| 编排        | LangGraph（问答状态机）                        |
| 异步任务      | RQ + Redis                              |
| 向量库       | PostgreSQL + pgvector（HNSW 索引）          |
| Embedding | BAAI/bge-m3（1024 维，本地）                  |
| Rerank    | BAAI/bge-reranker-v2-m3（本地，仅排序不参与拒答判定）   |
| LLM       | OpenAI 兼容协议（本机/局域网 Ollama、vLLM、DeepSeek 等均可；不可用时自动降级为检索片段回显） |
| 解析        | pypdf / python-docx / 内置 txt、md；**无文本层 PDF 自动走 pdftoppm + RapidOCR 扫描件兜底** |
| 切块        | 条款感知切块（按 条/章/节 切 + 标题回填，可切回通用递归切块）   |
| 去重        | 入库侧 sha256 精确去重 + 检索侧 3-gram 重叠系数近似去重 |
| 前端        | Next.js 16 + React 19 + Tailwind 4 + lucide-react |

## 测试

前置：PostgreSQL 运行中（可联网或已有模型缓存）。

```bash
cd backend
.venv/bin/pytest                     # 单元测试（96 个，解析/切块/入库/检索/去重/权限/护栏/API/管理端/提示词与温度契约）
.venv/bin/python tests/e2e_smoke.py  # 端到端冒烟（真实 bge-m3 + reranker）
.venv/bin/python scripts/eval_no_answer.py  # No-Answer 端到端评测（44 条标注集，需 API + LLM 在线）
```

测试默认连接独立库 `knowledgepilot_test`（不存在时自动创建并灌入 `sql/schema.sql`）。
**不要指向开发库**：`clean_tables` 之类的 fixture 会整表清空，曾发生过一次全量测试
抹掉整个知识库的事故。`conftest.py` 会拒绝在非测试库上运行，除非显式设
`KP_ALLOW_DESTRUCTIVE_TESTS=1`。

`e2e_smoke.py` 会自动起 uvicorn + RQ worker、上传 txt/md 样例文档、轮询接入完成、走 chat 断言回答与引用，最后打印 PASS/FAIL 汇总并清理进程。检测到本地模型缓存时自动启用 HF 离线模式；如需强制联网下载可设 `KP_E2E_ONLINE=1`。

## 已知限制（demo 范围）

- **无鉴权**：角色在服务端写死（admin/manager/employee），demo 未实现登录体系；权限过滤逻辑在检索前 SQL 中生效。文档可见范围可用 `PUT /documents/{id}/permissions` 调整，但**管理端 `/admin/*` 接口无任何保护**，生产环境接入前必须补 SSO。
- **扫描件 OCR 兜底**：无文本层 / 纯图片型 PDF 会自动栅格化（pdftoppm，默认 200 DPI）并走 RapidOCR（onnxruntime CPU）提取文字，无需人工介入；受 `OCR_ENABLED`（`true`）/ `OCR_DPI`（`200`）控制。OCR 依赖系统 `poppler-utils` 与 Python 包 `rapidocr-onnxruntime`。
- **无 SSE 流式**：chat 为同步返回；前端以打字机效果呈现答案，打字为客户端动画而非真流式。
- **回答依赖外部 LLM**：回答需一个 OpenAI 兼容端点（本机 Ollama、局域网机器、或第三方 API 皆可，配置见「快速开始 §3」）。LLM 不可用时自动降级为检索片段回显（"根据资料：{top chunk 内容前缀}"）保证 demo 不中断，但此时 **Tier3 终审被跳过**，形似干扰项（如「劳动合同法规定的试用期上限是多少」）会带着本公司制度段落被放行。
- **阈值随语料漂移**：`ANSWER_GATE=0.45` 是按当前 demo 语料标定的。换语料后务必用 `tests/bench/calibrate_noanswer.py` 重新标定 —— 实测语料 15→35 篇时域外最高相似度会从 0.5256 漂到 0.5996。
- **单用户 · 无多租户**：会话已落库（chat 会写入 conversations/messages，`GET /conversations` 与 `GET /{id}/messages` 可查），但无用户体系、会话不按用户隔离；前端仍用 localStorage 记住当前会话。
- **引用内容**：`POST /chat` 已内联富化引用（原文摘录/页码/节标题），来源案卷抽屉在真实模式下可用；**不存在**独立的 `GET /chat/{id}/citations` 接口。
- **对象存储**：文件存本地 `/tmp/kp_uploads`，未接 S3。
- **二元拒答会浪费「部分命中」**：目前只有「回答 / 拒答」两种结果。实测有两条
  查询属于中间态 —— 语料命中了正确条款，却偏偏没有用户问的那个精确维度
  （「差旅报销要几个工作日」：资料写「次周周五统一打款」，有节点无数目；
  「违约最高赔多少」：资料写「违约金壹拾万元 + 直接经济损失」，损失不封顶因而
  「最高」并不存在）。这类当前一律拒答，评测中标记为 `BOUNDARY`、不计入主指标。
  下一步可引入三态输出（完整 / 部分 / 拒答），但三态会给形似干扰项多留一个可误踩的
  档位，必须先设计好作用域约束再动，否则会牺牲现在 19/19 的域外成绩。
- **评测集只有 44 条且语料较小**：4 篇文档 25 个块。结论足以定位设计缺陷，
  但不足以精确刻画长尾，换语料后请用 `scripts/eval_no_answer.py` 重新基线。

## 部署（Docker Compose）

`deploy/docker-compose.yml` 覆盖后端基础设施与 API/Worker 的容器化：

```bash
docker compose -f deploy/docker-compose.yml up -d --build
```

- `postgres`（pgvector）、`redis` 由镜像提供；
- `api` / `worker` 基于 `backend/Dockerfile`（python:3.11-slim + `pip install .`）构建；
- `api` 容器启动后需手动执行 schema 初始化：`docker compose exec -T postgres psql -U kp -d knowledgepilot < backend/sql/schema.sql`（首次），并确认模型缓存已挂载/可下载。

**前端不打包进 Compose**：demo 阶段前端用 `npm run dev` 本地运行（3000 端口，反代到 API）。两种模式分工：**Compose 管后端基础设施**，**前端本地 dev**。如需把前端也容器化，可为其加一个基于 `node:20` 的 `next build && next start` 镜像并 `depends_on: api`。

