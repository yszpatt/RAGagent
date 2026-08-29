from redis import Redis
from rq import Queue
from sqlalchemy import text

from app.core.config import settings
from app.db import SessionLocal
from app.ingestion.pipeline import run_ingestion

# Redis.from_url 是惰性连接：redis server 未启动时导入本模块不会失败。
redis_conn = Redis.from_url(settings.redis_url)
queue = Queue("ingestion", connection=redis_conn)


def _mark_document_failed(job, connection, type, value, traceback):
    """RQ 失败回调：在 worker 主进程执行（work-horse 硬崩时也保证触发）。

    run_ingestion 内部的 except 只能兜住 Python 异常；work-horse 被信号杀死
    （onnxruntime 段错误等）时协程体直接蒸发，documents.status 会永远卡在
    processing。此回调是最后防线：仅把 processing 状态翻转为 failed。
    """
    doc_id = job.args[1] if len(job.args) > 1 else None
    if doc_id is None:
        return
    with SessionLocal() as s:
        s.execute(text(
            "UPDATE documents SET status = 'failed', error_message = :m "
            "WHERE id = :i AND status = 'processing'"
        ), {"m": f"摄取进程异常终止: {type.__name__}: {value}", "i": str(doc_id)})
        s.commit()


def enqueue_ingestion(path: str, document_id, workspace_id=None, roles=None):
    return queue.enqueue(run_ingestion, path, document_id, workspace_id, roles,
                         on_failure=_mark_document_failed,
                         job_timeout="1h")
