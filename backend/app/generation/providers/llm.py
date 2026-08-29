"""LLM Provider：Ollama 原生 + OpenAI 兼容协议。

设计要点
--------
**为什么必须是 OpenAI 兼容协议？**
部署形态可能有：本机 Ollama、局域网另一台机器的 Ollama、vLLM / Xinference / LM Studio、
DeepSeek、Moonshot、通义千问(兼容模式)、SiliconFlow、OpenAI ……
为每一家写适配器是维护灾难。Chat Completions 协议已成为事实标准，
一个客户端即可覆盖全部场景，切换只改环境变量。

**关于 NO_ANSWER_MARKER**
P0-1 实测发现：reranker 绝对分数在域内外分布重叠，用它做阈值门控会误杀 40% 正确答案。
故把「能不能回答」的终审权交给 LLM —— LLM 读的是上下文内容本身，
判断不依赖任何分数分布，因此不受语料规模增长影响（绝对阈值会漂移，内容判断不会）。

**关于 SYSTEM_PROMPT 的两类错配（实测 44 条，见 scripts/eval_no_answer.py）**
Tier3 的拒答错误不是单一原因，而是两种性质相反的错配，必须分开写规则：

    甲类 术语错配（口语 vs 书面语）→ 应当对齐后回答。
        「这合同能作废吗」问「作废」，资料写「解除」。不映射就会误杀。
    乙类 作用域错配（内部规定 vs 外部通用）→ 不得对齐，必须拒答。
        「一般公司的违约金是怎么算的」问的是普遍做法，
        资料里只有本合同约定，拿它充当通用答案就是越权编造。

只放宽映射（试图修甲类）会让乙类漏出去：实测域内 +1、域外 -1，净零。
两类规则同时写才拿到两全：域内 24/25、域外 19/19。
"""
import re

import httpx

from app.generation.providers.base import LLMProvider

# 上下文不足以回答时，要求 LLM 输出且仅输出该标记
NO_ANSWER_MARKER = "__NO_ANSWER__"

SYSTEM_PROMPT = """你是一个企业知识库问答助手，只能依据给定的【参考资料】回答问题。

严格遵循以下规则：
1. 仅使用【参考资料】中的信息作答，不得使用资料外的知识，不得编造。
2. 引用资料时，在相关句末用方括号标注资料编号，例如 [1]、[2]。
3. 若【参考资料】中的信息不足以回答该问题，只输出一行标记：__NO_ANSWER__
4. 触发第 3 条时不要解释原因，不要输出任何其他文字。
5. 回答使用与问题相同的语言，简明扼要。

判断能否回答时，注意区分以下两类错配：

【甲类：术语错配 —— 应当对齐，允许回答】
员工习惯用口语提问，资料是书面语。先做同义映射再判断，例如：
    作废 / 不算数 / 取消      →  解除、终止、无效
    不给钱 / 拖着不付 / 赖账  →  逾期付款、违约
    要多久 / 几个工作日       →  资料中写明的时间节点或周期
映射成立且资料中确有对应事实的，正常作答。
允许基于单条资料做一步直接推理（例如由「严重违约可单方解除合同」推出「满足该条件时可以作废」）。
禁止拼接多条资料、推测出其中任何一条都没有写的事实。

【乙类：作用域错配 —— 不得对齐，必须拒答】
若问题问的是普遍情况或外部规定，而【参考资料】只是本公司或本合同的内部规定，
则不得用内部规定充当通用答案，按第 3 条输出 __NO_ANSWER__。
作用域越界的常见信号：
    一般 / 通常 / 大多数公司 / 业界 / 行情
    国家规定 / 法律规定 / 劳动法 / 民法典 / 某某法规定 / 行业标准"""

_USER_TEMPLATE = """【参考资料】
{context}

【问题】
{question}"""


def build_prompt(question: str, context: str) -> str:
    """组装用户消息（参考资料 + 问题）。system 指令在 provider 内分别传入。"""
    return _USER_TEMPLATE.format(context=context, question=question)


def extract_no_answer(text: str) -> bool:
    """判断 LLM 输出是否为「无法回答」标记。

    兼容模型偶尔包裹 markdown 代码块 / 空白 / 全角括号等噪声。
    """
    if not text:
        return False
    t = text.strip().strip("`").strip()
    t = t.replace("＿", "_")
    return t == NO_ANSWER_MARKER or NO_ANSWER_MARKER in t


class OllamaLLM(LLMProvider):
    """Ollama 原生接口（/api/generate）。适合本机或局域网裸 Ollama 服务。"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b",
                 timeout: int = 120, temperature: float = 0.0):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._temperature = temperature

    async def generate(self, prompt: str, context: str) -> str:
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{build_prompt(prompt, context)}\n\n回答："
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": full_prompt, "stream": False,
                      "options": {"temperature": self._temperature}},
            )
            resp.raise_for_status()
            return resp.json()["response"]


class OpenAICompatLLM(LLMProvider):
    """OpenAI Chat Completions 兼容接口。

    覆盖场景（只需改 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）：
        局域网 Ollama    http://192.168.x.x:11434/v1      key 任意占位
        本机 Ollama      http://localhost:11434/v1        key 任意占位
        vLLM / Xinference / LM Studio                    各自 /v1 端点
        DeepSeek        https://api.deepseek.com/v1
        Moonshot/Kimi   https://api.moonshot.cn/v1
        通义千问(兼容)   https://dashscope.aliyuncs.com/compatible-mode/v1
        SiliconFlow     https://api.siliconflow.cn/v1
        OpenAI          https://api.openai.com/v1
    """

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: int = 120,
                 temperature: float = 0.0):
        self._base_url = _normalize_base_url(base_url)
        self._model = model
        # Ollama / vLLM 等本地服务不校验 key，但未传 Authorization 会被部分网关拒，故给占位值
        self._api_key = api_key or "EMPTY"
        self._timeout = timeout
        self._temperature = temperature

    async def generate(self, prompt: str, context: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(prompt, context)},
            ],
            "stream": False,
            # 必须显式下发：不传时 Ollama 取默认 0.8，Tier3 判定会随机翻转。
            "temperature": self._temperature,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"LLM 响应格式异常: {str(data)[:300]}") from e


def _normalize_base_url(url: str) -> str:
    """归一化 base_url：去尾斜杠，并确保以 /v1 结尾。

    用户可能填 http://host:11434、http://host:11434/v1、
    甚至 http://host:11434/v1/chat/completions，这里统一到 /v1。
    """
    u = (url or "").strip().rstrip("/")
    if not u:
        raise ValueError("LLM_BASE_URL 未配置")
    u = re.sub(r"/chat/completions$", "", u)
    if not u.endswith("/v1"):
        u = f"{u}/v1"
    return u
