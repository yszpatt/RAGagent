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
"""
import re

import httpx

from app.generation.providers.base import LLMProvider

# 上下文不足以回答时，要求 LLM 输出且仅输出该标记
NO_ANSWER_MARKER = "__NO_ANSWER__"

SYSTEM_PROMPT = """你是一个企业知识库问答助手，只能依据给定的【参考资料】回答问题。

严格遵循以下规则：
1. 仅使用【参考资料】中的信息作答，不得使用资料外的知识，不得推测或编造。
2. 引用资料时，在相关句末用方括号标注资料编号，例如 [1]、[2]。
3. 若【参考资料】中的信息不足以回答该问题，只输出一行标记：__NO_ANSWER__
4. 触发第 3 条时不要解释原因，不要输出任何其他文字。
5. 回答使用与问题相同的语言，简明扼要。"""

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
                 timeout: int = 120):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate(self, prompt: str, context: str) -> str:
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"{build_prompt(prompt, context)}\n\n回答："
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": full_prompt, "stream": False},
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

    def __init__(self, base_url: str, model: str, api_key: str = "", timeout: int = 120):
        self._base_url = _normalize_base_url(base_url)
        self._model = model
        # Ollama / vLLM 等本地服务不校验 key，但未传 Authorization 会被部分网关拒，故给占位值
        self._api_key = api_key or "EMPTY"
        self._timeout = timeout

    async def generate(self, prompt: str, context: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_prompt(prompt, context)},
            ],
            "stream": False,
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
