import hashlib
import json
import uuid
from pathlib import Path
import aiofiles
from fastapi import APIRouter, Form, Request, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from app.db import SessionLocal
from app.generation.providers.embedding import EmbeddingConfig
from app.ingestion.tasks import enqueue_ingestion
from app.services.audit import write_audit
from app.services.context import default_workspace_id

router = APIRouter(prefix="/documents", tags=["documents"])

# 前端设置页下发的 embedding 配置经由此请求头透传给后端 / worker。
EMBEDDING_CFG_HEADER = "x-kp-embedding-cfg"


def _embedding_cfg_from_request(request: Request) -> EmbeddingConfig | None:
    return EmbeddingConfig.from_header(request.headers.get(EMBEDDING_CFG_HEADER))

UPLOAD_DIR = Path("/tmp/kp_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

VALID_ROLES = ("admin", "manager", "employee")


def _parse_roles(raw: str | None) -> list[str] | None:
    """上传表单的 role_visibility（JSON 数组字符串）→ 校验后的角色列表。

    缺省/解析失败 → None（沿用全角色开放）；指定非法值直接 422。
    """
    if not raw:
        return None
    try:
        roles = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="role_visibility 需为 JSON 数组")
    if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
        raise HTTPException(status_code=422, detail="role_visibility 需为字符串数组")
    invalid = [r for r in roles if r not in VALID_ROLES]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"未知角色：{invalid}（可选 admin/manager/employee）",
        )
    if not roles:
        raise HTTPException(status_code=422, detail="role_visibility 不能为空")
    return sorted(set(roles))


def _doc_or_404(s, doc_uuid: uuid.UUID):
    row = s.execute(sql_text(
        "SELECT id, title, status, error_message, created_at FROM documents WHERE id = :id"
    ), {"id": doc_uuid}).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return row


@router.get("")
async def list_documents():
    """列出全部文档（含可见角色与 chunk 数量），供知识库页展示。"""
    with SessionLocal() as s:
        rows = s.execute(sql_text("""
            SELECT d.id, d.title, d.source_type, d.status, d.error_message, d.created_at,
                   COALESCE(array_agg(DISTINCT dp.role) FILTER (WHERE dp.role IS NOT NULL), '{}') AS roles,
                   (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunk_count
            FROM documents d
            LEFT JOIN document_permissions dp ON dp.document_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
        """)).fetchall()
    return {
        "data": [
            {
                "document_id": str(r[0]),
                "title": r[1],
                "source_type": r[2],
                "status": r[3],
                "error_message": r[4],
                "created_at": str(r[5]),
                "roles": [str(x) for x in (r[6] or [])],
                "chunk_count": int(r[7]),
            }
            for r in rows
        ],
        "meta": {"total": len(rows)},
    }


@router.get("/{document_id}")
async def get_document(document_id: str):
    """查询文档接入状态（demo 用，供前端轮询）。"""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的文档 ID")
    with SessionLocal() as s:
        row = _doc_or_404(s, doc_uuid)
    return {"data": {"document_id": str(row[0]), "title": row[1], "status": row[2],
                     "error_message": row[3], "created_at": str(row[4])}}


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """删除文档（chunks/权限级联删除），并尽力清理磁盘上的原始文件。"""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的文档 ID")
    with SessionLocal() as s:
        row = _doc_or_404(s, doc_uuid)
        # storage_path 不在查询列里，取一次用于清理文件
        path_row = s.execute(sql_text(
            "SELECT storage_path FROM documents WHERE id = :id"
        ), {"id": doc_uuid}).fetchone()
        s.execute(sql_text("DELETE FROM documents WHERE id = :id"), {"id": doc_uuid})
        s.commit()
    if path_row and path_row[0]:
        try:
            Path(path_row[0]).unlink(missing_ok=True)
        except OSError:
            pass  # 文件清理失败不影响删除结果（DB 是事实来源）
    write_audit("delete", query_text=row[1])
    return {"data": {"document_id": str(row[0]), "deleted": True}}


@router.post("/{document_id}/reingest")
async def reingest_document(document_id: str, request: Request):
    """用已存储的原始文件重新接入（清空旧 chunk 后重跑管线）。"""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的文档 ID")
    with SessionLocal() as s:
        row = s.execute(sql_text(
            "SELECT storage_path FROM documents WHERE id = :id"
        ), {"id": doc_uuid}).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        storage_path = row[0]
    if not storage_path or not Path(storage_path).exists():
        raise HTTPException(status_code=422, detail="原始文件已不存在，请删除后重新上传")
    with SessionLocal() as s:
        s.execute(sql_text(
            "UPDATE documents SET status = 'processing', error_message = NULL WHERE id = :id"
        ), {"id": doc_uuid})
        s.commit()
    write_audit("upload", query_text=f"重新解析 {Path(storage_path).name}")
    job = enqueue_ingestion(
        storage_path, doc_uuid,
        embedding_cfg=_embedding_cfg_from_request(request),
    )
    return {"document_id": str(doc_uuid), "job_id": str(job.id), "status": "processing"}


class PermissionsUpdate(BaseModel):
    roles: list[str]


@router.put("/{document_id}/permissions")
async def update_permissions(document_id: str, payload: PermissionsUpdate):
    """设置文档角色可见范围（检索前过滤的数据来源），管理员始终保留可见。"""
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效的文档 ID")
    roles = [r for r in payload.roles if r in VALID_ROLES]
    if not roles:
        raise HTTPException(status_code=422, detail="roles 不能为空（可选 admin/manager/employee）")
    roles = sorted(set(roles) | {"admin"})
    with SessionLocal() as s:
        row = s.execute(sql_text(
            "SELECT title FROM documents WHERE id = :id"
        ), {"id": doc_uuid}).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        s.execute(sql_text(
            "DELETE FROM document_permissions WHERE document_id = :id"
        ), {"id": doc_uuid})
        for r in roles:
            s.execute(sql_text(
                "INSERT INTO document_permissions (id, document_id, role) "
                "VALUES (:id, :doc, :role) ON CONFLICT (document_id, role) DO NOTHING"
            ), {"id": str(uuid.uuid4()), "doc": doc_uuid, "role": r})
        s.commit()
    write_audit("permission_change", query_text=f"{row[0]} → {'+'.join(roles)}")
    return {"data": {"document_id": str(doc_uuid), "roles": roles}}


def _find_duplicate(workspace_id, content_hash: str):
    """同工作区内已有相同内容则返回 (id, title, status)，否则 None。"""
    with SessionLocal() as s:
        return s.execute(sql_text("""
            SELECT id, title, status FROM documents
            WHERE workspace_id = :ws AND content_hash = :h
            LIMIT 1
        """), {"ws": workspace_id, "h": content_hash}).fetchone()


@router.post("/upload")
async def upload(file: UploadFile = File(...), role_visibility: str = Form(default=""),
                 force: bool = Form(default=False), request: Request = None):
    """上传文档并入队接入。

    三件事与旧实现不同：
      1. **落 documents 行再入队**（status=pending）。旧实现只在 worker 里
         `_upsert_document` 才建行，导致前端拿到 document_id 后立刻轮询
         GET /documents/{id} 会 404 —— 上传与建行之间存在竞态窗口。
      2. **按内容 sha256 去重**。实测同一份合同可被上传 3 次，9 个 chunk 里
         4 个冗余，重复块挤占 top-k 名额压低准确度。命中重复返回 409，
         附带已存在文档的信息。
      3. 文件边写边算哈希，不额外读一遍磁盘。

    force=true 的语义是**重建同一份文档的索引并覆盖原记录**，而不是新增副本
    （新增副本等于把重复块问题又造回来）。典型场景是切块策略变更后重新入库，
    此时 documents 行被复用，旧 chunk / 旧权限先清空，再重新入队。
    """
    doc_id = uuid.uuid4()
    roles = _parse_roles(role_visibility)
    # 防路径穿越：剥离目录部分（POSIX 用 /，Windows 用 \）
    safe_name = file.filename.replace("\\", "/").rsplit("/", 1)[-1] or "file"
    path = UPLOAD_DIR / f"{doc_id}_{safe_name}"

    hasher = hashlib.sha256()
    async with aiofiles.open(path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            hasher.update(chunk)
            await f.write(chunk)
    content_hash = hasher.hexdigest()

    workspace_id = default_workspace_id()
    dup = _find_duplicate(workspace_id, content_hash)
    replaced = False

    if dup is not None and not force:
        # 重复文件不留残骸，磁盘与 DB 都只保留最早那一份
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=409,
            detail={
                "message": "该文档内容已存在，未重复入库",
                "document_id": str(dup[0]),
                "title": dup[1],
                "status": dup[2],
                "hint": "确需重建索引（如切块策略变更）请带 force=true 重新上传",
            },
        )

    source_type = Path(safe_name).suffix.lower().lstrip(".") or "unknown"
    with SessionLocal() as s:
        if dup is not None:
            # force 覆盖：复用已有行，让「同工作区同内容只有一份」在 DB 层恒成立。
            # 旧权限一并清掉，使本次上传的 role_visibility 成为权威值
            # （add_chunks 用 ON CONFLICT DO NOTHING，不清会残留旧角色）。
            replaced = True
            doc_id = dup[0]
            old_path = s.execute(sql_text(
                "SELECT storage_path FROM documents WHERE id = :id"
            ), {"id": doc_id}).scalar()
            s.execute(sql_text("DELETE FROM chunks WHERE document_id = :id"), {"id": doc_id})
            s.execute(sql_text(
                "DELETE FROM document_permissions WHERE document_id = :id"
            ), {"id": doc_id})
            s.execute(sql_text("""
                UPDATE documents
                   SET title = :title, source_type = :stype, storage_path = :path,
                       status = 'pending', error_message = NULL, updated_at = now()
                 WHERE id = :id
            """), {"id": doc_id, "title": safe_name, "stype": source_type, "path": str(path)})
            if old_path and old_path != str(path):
                try:
                    Path(old_path).unlink(missing_ok=True)
                except OSError:
                    pass
        else:
            s.execute(sql_text("""
                INSERT INTO documents (id, workspace_id, title, source_type, storage_path,
                                       status, content_hash)
                VALUES (:id, :ws, :title, :stype, :path, 'pending', :hash)
                ON CONFLICT (id) DO UPDATE SET status = 'pending'
            """), {"id": doc_id, "ws": workspace_id, "title": safe_name,
                   "stype": source_type, "path": str(path), "hash": content_hash})
        s.commit()

    job = enqueue_ingestion(
        str(path), doc_id, roles=roles,
        embedding_cfg=_embedding_cfg_from_request(request) if request else None,
    )
    write_audit("upload", query_text=f"{safe_name}{'（覆盖重建）' if replaced else ''}")
    return {"document_id": str(doc_id), "job_id": str(job.id), "status": "pending",
            "content_hash": content_hash, "duplicate": False, "replaced": replaced}
