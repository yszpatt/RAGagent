"""管理端接口：审计日志查询 + 使用指标（对应设计文档 §6.4，demo 单租户无鉴权）。"""
from fastapi import APIRouter
from sqlalchemy import text as sql_text

from app.db import SessionLocal

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs")
async def audit_logs(action: str | None = None, limit: int = 50, offset: int = 0):
    """审计日志（按时间倒序），可按动作过滤；actor 取默认用户（demo 无鉴权）。"""
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    with SessionLocal() as s:
        rows = s.execute(sql_text("""
            SELECT a.id, a.action, a.query_text, a.created_at,
                   u.external_id, u.role AS user_role,
                   COALESCE(array_length(a.retrieved_chunk_ids, 1), 0) AS hit_count
            FROM audit_logs a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE (:action IS NULL OR a.action = :action)
            ORDER BY a.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"action": action, "limit": limit, "offset": offset}).fetchall()
        total = s.execute(sql_text(
            "SELECT count(*) FROM audit_logs WHERE (:action IS NULL OR action = :action)"
        ), {"action": action}).scalar()
    return {
        "data": [
            {
                "id": str(r[0]),
                "action": r[1],
                "query_text": r[2],
                "created_at": str(r[3]),
                "actor": r[4] or "anonymous",
                "actor_role": r[5],
                "hit_count": int(r[6] or 0),
            }
            for r in rows
        ],
        "meta": {"total": int(total or 0), "limit": limit, "offset": offset},
    }


@router.get("/metrics")
async def metrics():
    """使用指标：口径对应产品文档 §3.1。

    采纳率（需点赞/引用点击行为埋点）与时延分位（需计时埋点）暂缺数据源，返回 null。
    """
    with SessionLocal() as s:
        doc_rows = s.execute(sql_text(
            "SELECT status, count(*) FROM documents GROUP BY status"
        )).fetchall()
        msg = s.execute(sql_text("""
            SELECT count(*) AS total,
                   count(*) FILTER (WHERE no_answer) AS no_answer,
                   count(*) FILTER (WHERE COALESCE(jsonb_array_length(citations), 0) > 0) AS with_citations
            FROM messages WHERE role = 'assistant'
        """)).fetchone()
        weekly = s.execute(sql_text("""
            SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS day,
                   count(*) AS queries
            FROM audit_logs
            WHERE action = 'query' AND created_at > now() - interval '7 days'
            GROUP BY 1 ORDER BY 1
        """)).fetchall()
        today_queries = s.execute(sql_text(
            "SELECT count(*) FROM audit_logs "
            "WHERE action = 'query' AND created_at >= date_trunc('day', now())"
        )).scalar()
        recent = s.execute(sql_text("""
            SELECT a.query_text, COALESCE(m.no_answer, false) AS no_answer,
                   to_char(a.created_at, 'HH24:MI') AS at
            FROM audit_logs a
            LEFT JOIN messages m ON m.id = a.response_ref
            WHERE a.action = 'query'
            ORDER BY a.created_at DESC
            LIMIT 8
        """)).fetchall()

    by_status = {r[0]: int(r[1]) for r in doc_rows}
    total_docs = sum(by_status.values())
    total_docs_statused = total_docs or 1
    assistant_total = int(msg[0] or 0) if msg else 0
    no_answer = int(msg[1] or 0) if msg else 0
    with_citations = int(msg[2] or 0) if msg else 0

    return {
        "data": {
            "today_queries": int(today_queries or 0),
            "no_answer_rate": round(no_answer / assistant_total * 100, 1) if assistant_total else None,
            "citation_rate": round(with_citations / assistant_total * 100, 1) if assistant_total else None,
            "parse_fail_rate": round(by_status.get("failed", 0) / total_docs_statused * 100, 1) if total_docs else None,
            "acceptance_rate": None,  # 待采纳行为埋点（点赞/引用点击）
            "latency_p95": None,  # 待计时埋点
            "documents": {
                "total": total_docs,
                "completed": by_status.get("completed", 0),
                "failed": by_status.get("failed", 0),
                "processing": by_status.get("processing", 0) + by_status.get("pending", 0),
            },
            "conversations": {
                "assistant_messages": assistant_total,
                "no_answer": no_answer,
            },
            "weekly_queries": [{"day": r[0], "queries": int(r[1])} for r in weekly],
            "recent_questions": [
                {"query": r[0], "no_answer": bool(r[1]), "at": r[2]} for r in recent
            ],
        }
    }
