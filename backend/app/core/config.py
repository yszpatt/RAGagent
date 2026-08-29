from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://kp:kp@localhost:5432/knowledgepilot"
    redis_url: str = "redis://localhost:6379"
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    rerank_threshold: float = 0.3
    no_answer_message: str = "未找到相关信息，请尝试换个问法。"

    # ---- 切块（P1-3/P1-4）：条款感知切块 ----
    # clause_aware 面向中文企业文档（按 条/章/节 切，标题回填，短条不合并）；
    # recursive   为通用递归切块，作为回退与非中文语料的选择。
    chunker: str = "clause_aware"   # clause_aware | recursive
    chunk_size: int = 500
    chunk_overlap: int = 50
    chunk_min_size: int = 80        # 短于此且无标题的引导段会并入其后的条款块

    # ---- LLM 接入（P0-2）：OpenAI 兼容协议覆盖局域网 / 第三方服务 ----
    # ollama        : 走 Ollama 原生 /api/generate
    # openai_compat : 走 /v1/chat/completions，覆盖局域网 Ollama、vLLM、Xinference、
    #                 DeepSeek、Moonshot、通义千问(兼容模式)、SiliconFlow、OpenAI ……
    llm_provider: str = "ollama"
    llm_base_url: str = ""      # 留空则回落到 ollama_base_url
    llm_api_key: str = ""       # Ollama 不需要真实 key，填占位值即可
    llm_timeout: int = 120

    # ---- No-Answer 两级判定（P0-1）----
    # 实测：reranker 绝对分数域内外分布重叠，用它做门控会误杀 40% 正确答案；
    # 而 bge-m3 余弦相似度存在干净间隙。故职责重划：
    #   Tier1 门控 = embedding 余弦（宽松，宁可放过不可误杀）
    #   Tier2 精排 = reranker 仅排序，不参与判定
    #   Tier3 终审 = LLM 判断上下文是否真能回答
    # 0.45 由 44 条真实查询（30 域内 / 14 域外）标定，且刻意不取 F1 最优点。
    #
    # 条款感知切块上线后，同批查询实测：
    #   阈值   误杀(域内被拒)  放过(域外进入)   F1     备注
    #   0.40        0             6          0.909
    #   0.45        0             5          0.923   ← 采用
    #   0.50        0             4          0.938   F1 最优
    #   0.55        1             4          0.921   改前默认值（条款切块前误杀高达 11/30）
    #
    # 为什么不取 F1 最优的 0.50：域内最低相似度 0.5438，0.50 只剩 0.044 余量。
    # 而阈值随语料规模漂移是**实测过的** —— 语料 15→35 篇时域外最高相似度
    # 0.5256→0.5996，一漂就误杀。0.45 对域内最低值留 0.094 余量。
    #
    # 定位：Tier1 只是廉价预筛，误杀的代价（本该答对的直接拒答，用户无解）
    # 远大于放过的代价（多跑一次 LLM，由 Tier3 按内容判回拒答）—— 放过的 5 条
    # 全是「劳动合同法 / 民法典」这类形似干扰项，正是 Tier3 要处理的。
    # 换语料后请用 backend/tests/bench/calibrate_noanswer.py 重新标定。
    answer_gate: float = 0.45          # Tier1 阈值，用 calibrate_noanswer.py 标定
    answer_gate_enabled: bool = True   # 关掉则退回旧的 rerank_threshold 单阈值行为
    llm_final_check: bool = True       # Tier3 LLM 终审开关

    # ---- 检索去重（P1-5）----
    # 结果里近重复块（3-gram 重叠系数 >= 该值）只保留排在最前的那个。
    # 用重叠系数 |A∩B|/min(|A|,|B|) 而非 Jaccard：去重要回答的是「这块是否已被
    # 保留的某块覆盖」，是不对称问题；Jaccard 惩罚长度差，实测 30 字与其 35 字
    # 扩写版只有 0.794，会漏判真正的近重复。
    # 解决：同一文档重复上传、或不同文档含有相同套话条款时，top-k 被重复内容挤占。
    dedup_enabled: bool = True
    dedup_threshold: float = 0.90


settings = Settings()
