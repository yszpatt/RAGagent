import uuid
from pathlib import Path
import aiofiles
from fastapi import APIRouter, UploadFile, File
from app.ingestion.tasks import enqueue_ingestion

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path("/tmp/kp_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
