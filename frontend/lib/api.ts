// 后端 API 客户端。所有请求走 /api/*（next.config rewrite 反代到 FastAPI）。

import type { ChatResponse, DocStatus } from "./types";

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

export async function ask(query: string): Promise<ChatResponse> {
  const res = await fetch("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return (await res.json()) as ChatResponse;
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
