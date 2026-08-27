import uuid
from pathlib import Path
import aiofiles
from fastapi import APIRouter, UploadFile, File, HTTPException
from sqlalchemy import text as sql_text
from app.db import SessionLocal
from app.ingestion.tasks import enqueue_ingestion

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path("/tmp/kp_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/{document_id}")
async def get_document(document_id: str):
    """查询文档接入状态（demo 用，供前端轮询）。"""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的文档 ID")
    with SessionLocal() as s:
        row = s.execute(sql_text(
            "SELECT id, title, status, error_message, created_at FROM documents WHERE id = :id"
        ), {"id": doc_uuid}).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"data": {"document_id": str(row[0]), "title": row[1], "status": row[2],
                     "error_message": row[3], "created_at": str(row[4])}}


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    doc_id = uuid.uuid4()
    # 防路径穿越：剥离目录部分（POSIX 用 /，Windows 用 \）
    safe_name = file.filename.replace("\\", "/").rsplit("/", 1)[-1] or "file"
    path = UPLOAD_DIR / f"{doc_id}_{safe_name}"
    async with aiofiles.open(path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)
    job = enqueue_ingestion(str(path), doc_id)
    return {"document_id": str(doc_id), "job_id": str(job.id), "status": "pending"}
