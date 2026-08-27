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
    path = UPLOAD_DIR / f"{doc_id}_{file.filename}"
    async with aiofiles.open(path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            await f.write(chunk)
    job = enqueue_ingestion(str(path), doc_id)
    return {"document_id": str(doc_id), "job_id": str(job.id), "status": "pending"}
