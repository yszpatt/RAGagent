import httpx
from app.generation.providers.base import LLMProvider


class OllamaLLM(LLMProvider):
    """demo 用 Ollama 本地模型，Provider 抽象保留 OpenAI/Claude/Gemini 切换能力。"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:7b"):
        self._base_url = base_url
        self._model = model

    async def generate(self, prompt: str, context: str) -> str:
        full_prompt = f"基于以下资料回答问题：\n\n{context}\n\n问题：{prompt}"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={"model": self._model, "prompt": full_prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json()["response"]
