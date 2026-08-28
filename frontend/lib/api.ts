// 后端 API 客户端。所有请求走 /api/*（next.config rewrite 反代到 FastAPI）。

import type { ChatResponse, Citation, DocStatus, DocumentMeta, Role } from "./types";

async function parseError(res: Response): Promise<string> {
  try {
    const text = await res.text();
    try {
      const data = JSON.parse(text) as { detail?: string };
      if (data.detail) return String(data.detail);
    } catch {
      /* 非 JSON 响应 */
    }
    return text.slice(0, 200) || `请求失败 (${res.status})`;
  } catch {
    return `请求失败 (${res.status})`;
  }
}

export async function ask(query: string, conversationId?: string): Promise<ChatResponse> {
  const res = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      conversationId ? { query, conversation_id: conversationId } : { query },
    ),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as ChatResponse;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  last_message_at: string | null;
  message_count: number;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await fetch("/api/v1/conversations", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()).data as ConversationSummary[];
}

export interface MessagePayload {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  no_answer: boolean;
  created_at: string;
}

export async function fetchMessages(conversationId: string): Promise<MessagePayload[]> {
  const res = await fetch(`/api/v1/conversations/${conversationId}/messages`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()).data as MessagePayload[];
}

export interface UploadResult {
  document_id: string;
  job_id: string;
  status: string;
}

export async function uploadDocument(file: File): Promise<UploadResult> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/v1/documents/upload", {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as UploadResult;
}

export interface DocumentStatusPayload {
  document_id: string;
  title: string;
  status: DocStatus;
  error_message: string | null;
  created_at: string;
}

export async function fetchDocument(id: string): Promise<DocumentStatusPayload> {
  const res = await fetch(`/api/v1/documents/${id}`);
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { data: DocumentStatusPayload };
  return body.data;
}

/** GET /documents：后端文档列表 → 前端 DocumentMeta */
export async function listDocuments(): Promise<DocumentMeta[]> {
  const res = await fetch("/api/v1/documents", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as {
    data: Array<{
      document_id: string;
      title: string;
      source_type: string;
      status: DocStatus;
      error_message: string | null;
      created_at: string;
      roles: Role[];
      chunk_count: number;
    }>;
  };
  return body.data.map((d) => ({
    id: d.document_id,
    title: d.title,
    ext: d.source_type,
    status: d.status,
    errorMessage: d.error_message,
    roles: d.roles,
    uploadedAt: Date.parse(d.created_at) || 0,
    chunkCount: d.chunk_count,
  }));
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`/api/v1/documents/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function reingestDocument(id: string): Promise<void> {
  const res = await fetch(`/api/v1/documents/${id}/reingest`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
}

export async function updateDocumentPermissions(
  id: string,
  roles: Role[],
): Promise<Role[]> {
  const res = await fetch(`/api/v1/documents/${id}/permissions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ roles }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const body = (await res.json()) as { data: { roles: Role[] } };
  return body.data.roles;
}

export interface AuditRow {
  id: string;
  action: string;
  query_text: string | null;
  created_at: string;
  actor: string;
  actor_role: string | null;
  hit_count: number;
}

export async function fetchAuditLogs(params?: {
  action?: string;
  limit?: number;
}): Promise<AuditRow[]> {
  const qs = new URLSearchParams();
  if (params?.action) qs.set("action", params.action);
  qs.set("limit", String(params?.limit ?? 100));
  const res = await fetch(`/api/v1/admin/audit-logs?${qs.toString()}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()).data as AuditRow[];
}

export interface MetricsPayload {
  today_queries: number;
  no_answer_rate: number | null;
  citation_rate: number | null;
  parse_fail_rate: number | null;
  acceptance_rate: number | null;
  latency_p95: string | null;
  documents: { total: number; completed: number; failed: number; processing: number };
  conversations: { assistant_messages: number; no_answer: number };
  weekly_queries: Array<{ day: string; queries: number }>;
  recent_questions: Array<{ query: string; no_answer: boolean; at: string }>;
}

export async function fetchMetrics(): Promise<MetricsPayload> {
  const res = await fetch("/api/v1/admin/metrics", { cache: "no-store" });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()).data as MetricsPayload;
}

/** 探测后端是否可达（/health 经 rewrite 反代） */
export async function checkBackend(timeoutMs = 1500): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const res = await fetch("/health", { signal: controller.signal, cache: "no-store" });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}
