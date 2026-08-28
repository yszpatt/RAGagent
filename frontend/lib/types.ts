// 与后端契约 + 前端内部状态的核心类型。

export type Role = "admin" | "manager" | "employee";

export type DocStatus = "pending" | "processing" | "completed" | "failed";

/** POST /api/v1/chat 响应（现有后端契约） */
export interface Citation {
  chunk_id: string;
  page: number | null;
  /** 以下字段由后端详情回填（_enrich_citations），可能缺失 */
  document_title?: string | null;
  section?: string | null;
  excerpt?: string | null;
}

export interface ChatResponse {
  answer: string;
  no_answer: boolean;
  citations: Citation[];
  /** 后端已持久化时返回，前端用于续聊与列表刷新 */
  conversation_id?: string | null;
  message_id?: string | null;
}

/** 一轮问答 */
export interface Turn {
  id: string;
  query: string;
  answer: string;
  no_answer: boolean;
  citations: Citation[];
  /** 完成时间（epoch ms） */
  at: number;
}

export interface Conversation {
  id: string;
  title: string;
  turns: Turn[];
  updatedAt: number;
}

export interface DocumentMeta {
  id: string;
  title: string;
  ext: string;
  status: DocStatus;
  errorMessage?: string | null;
  roles: Role[];
  uploadedAt: number;
  sizeLabel?: string;
  /** 已入库 chunk 数（后端列表接口提供） */
  chunkCount?: number;
}

/** 来源查看器中的单条引用 */
export interface SourceRef {
  /** 展示用编号，如 引-01 */
  ref: string;
  title: string;
  page: number | null;
  section?: string | null;
  excerpt?: string;
  chunkId?: string;
}
