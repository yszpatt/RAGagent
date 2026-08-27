from redis import Redis
from rq import Queue

from app.core.config import settings
from app.ingestion.pipeline import run_ingestion

# Redis.from_url 是惰性连接：redis server 未启动时导入本模块不会失败。
redis_conn = Redis.from_url(settings.redis_url)
queue = Queue("ingestion", connection=redis_conn)


def enqueue_ingestion(path: str, document_id, workspace_id=None):
    return queue.enqueue(run_ingestion, path, document_id, workspace_id)
