// 与后端契约 + 前端内部状态的核心类型。

export type Role = "admin" | "manager" | "employee";

export type DocStatus = "pending" | "processing" | "completed" | "failed";

/** POST /api/v1/chat 响应（现有后端契约） */
export interface Citation {
  chunk_id: string;
  page: number | null;
}

export interface ChatResponse {
  answer: string;
  no_answer: boolean;
  citations: Citation[];
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
