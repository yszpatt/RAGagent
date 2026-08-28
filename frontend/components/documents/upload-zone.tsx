"use client";

// 拖拽上传区：多选文件、类型预检（PDF/DOCX/MD/TXT）、逐文件状态反馈。
// 真实模式走后端 /api/v1/documents/upload + 状态轮询；演示模式本地模拟。

import { useCallback, useRef, useState } from "react";
import { FileUp, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn, formatBytes } from "@/lib/utils";

export const SUPPORTED_EXTS = ["pdf", "docx", "md", "txt"] as const;

export interface QueueItem {
  key: string;
  name: string;
  size: number;
  state: "rejected" | "uploading" | "parsing" | "done" | "failed";
  message?: string;
}

export function UploadZone({
  demo,
  onFileQueued,
  onDismiss,
}: {
  demo: boolean;
  /** 通过/未通过类型预检的文件交给父级渲染与处理 */
  onFileQueued: (file: File, key: string, rejected: boolean) => void;
  onDismiss: (key: string) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (files: FileList | File[]) => {
      Array.from(files).forEach((file) => {
        const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
        const rejected = !(SUPPORTED_EXTS as readonly string[]).includes(ext);
        const key = `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
        onFileQueued(file, key, rejected);
      });
    },
    [onFileQueued],
  );

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="上传文档：拖拽或点击选择文件"
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        if (e.dataTransfer.files.length) accept(e.dataTransfer.files);
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors",
        dragOver
          ? "border-indigo bg-indigo-wash"
          : "border-line-strong bg-paper hover:border-indigo/50",
      )}
    >
      <FileUp size={22} className="text-ink-faint" aria-hidden="true" />
      <p className="text-[13px] text-ink">
        拖拽文件到此处，或 <span className="font-medium text-indigo">点击选择</span>
      </p>
      <p className="text-xs text-ink-faint">
        支持 PDF / DOCX / MD / TXT · 可多选
        {demo && (
          <Badge tone="seal" className="ml-1.5">
            演示模式·模拟接入
          </Badge>
        )}
      </p>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.md,.txt"
        className="sr-only"
        onChange={(e) => {
          if (e.target.files?.length) accept(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function QueueList({
  items,
  onDismiss,
}: {
  items: QueueItem[];
  onDismiss: (key: string) => void;
}) {
  if (items.length === 0) return null;
  return (
    <ul className="mt-3 divide-y divide-line rounded-lg border border-line bg-paper">
      {items.map((it) => (
        <li key={it.key} className="flex items-center gap-3 px-3.5 py-2.5">
          <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
            {it.name}
            <span className="ml-2 font-mono text-[11px] text-ink-faint">
              {formatBytes(it.size)}
            </span>
          </span>
          {it.state === "uploading" && <Badge tone="indigo">上传中…</Badge>}
          {it.state === "parsing" && (
            <Badge tone="amber">
              <span
                className="inline-block size-1.5 animate-pulse rounded-full bg-amber motion-reduce:animate-none"
                aria-hidden="true"
              />
              解析中…
            </Badge>
          )}
          {it.state === "done" && <Badge tone="jade">✓ 接入完成</Badge>}
          {it.state === "failed" && (
            <Badge tone="seal" className="max-w-48 truncate" >
              ✕ {it.message ?? "失败"}
            </Badge>
          )}
          {it.state === "rejected" && (
            <Badge tone="amber">不支持的格式</Badge>
          )}
          <button
            onClick={() => onDismiss(it.key)}
            aria-label={`移除 ${it.name}`}
            className="rounded p-1 text-ink-faint hover:bg-porcelain hover:text-ink"
          >
            <X size={13} />
          </button>
        </li>
      ))}
    </ul>
  );
}
