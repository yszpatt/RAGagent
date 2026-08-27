from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://kp:kp@localhost:5432/knowledgepilot"
    redis_url: str = "redis://localhost:6379"
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_threshold: float = 0.3
    no_answer_message: str = "未找到相关信息，请尝试换个问法。"


settings = Settings()
