"use client";

// 知识库页：上传（真实接入 + 状态轮询）与文档列表。
// 真实模式：数据来自后端 GET /documents（列表/删除/重新解析均为真实接口）；
// 演示模式：展示占位文档集，可模拟接入/删除。

import { useCallback, useEffect, useMemo, useState } from "react";
import { LibraryBig, Trash2, RotateCcw, RefreshCw } from "lucide-react";
import { PageHeader, EmptyState } from "@/components/ui/page";
import { Badge, PreviewTag } from "@/components/ui/badge";
import { StatusBadge } from "@/components/documents/status-badge";
import {
  UploadZone,
  QueueList,
  type QueueItem,
} from "@/components/documents/upload-zone";
import { useDemoMode } from "@/lib/demo-context";
import { demoDocuments } from "@/lib/demo-data";
import {
  deleteDocument,
  fetchDocument,
  listDocuments,
  reingestAllDocuments,
  reingestDocument,
  uploadDocument,
} from "@/lib/api";
import { Time } from "@/components/ui/time";
import type { DocumentMeta } from "@/lib/types";
import { cn, newId, ROLE_LABELS } from "@/lib/utils";

const POLL_INTERVAL = 2000;
const POLL_MAX = 60;

type Filter = "all" | "processing" | "completed" | "failed";

export default function DocumentsPage() {
  const { demo } = useDemoMode();
  const [realDocs, setRealDocs] = useState<DocumentMeta[]>([]);
  const [listError, setListError] = useState("");
  const [demoDocs, setDemoDocs] = useState<DocumentMeta[]>(demoDocuments);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  // 两步删除确认：首次点击进入待确认态，3 秒未确认自动还原
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  // 批量重新摄入：提示文案 + 进行中锁定
  const [batchMsg, setBatchMsg] = useState("");
  const [batching, setBatching] = useState(false);

  const refreshList = useCallback(async () => {
    try {
      const docs = await listDocuments();
      setRealDocs(docs);
      setListError("");
    } catch (e) {
      setListError(e instanceof Error ? e.message : "获取文档列表失败");
    }
  }, []);

  // 真实模式：以后端列表为唯一数据源
  useEffect(() => {
    if (demo) return;
    void refreshList();
  }, [demo, refreshList]);

  const pollStatus = useCallback(
    async (docId: string) => {
      for (let i = 0; i < POLL_MAX; i++) {
        await sleep(POLL_INTERVAL);
        try {
          const data = await fetchDocument(docId);
          if (data.status === "completed" || data.status === "failed") {
            setQueue((q) =>
              q.map((it) =>
                it.key.startsWith(docId)
                  ? { ...it, state: data.status === "completed" ? ("done" as const) : ("failed" as const), message: data.error_message ?? undefined }
                  : it,
              ),
            );
            void refreshList();
            return;
          }
        } catch {
          // 网络抖动继续轮询
        }
      }
    },
    [refreshList],
  );

  const handleFileQueued = useCallback(
    (file: File, key: string, rejected: boolean) => {
      if (rejected) {
        setQueue((q) => [
          ...q,
          { key, name: file.name, size: file.size, state: "rejected" },
        ]);
        return;
      }
      if (demo) {
        // 演示：本地模拟接入流程
        setQueue((q) => [
          ...q,
          { key, name: file.name, size: file.size, state: "parsing" },
        ]);
        setTimeout(() => {
          setQueue((q) =>
            q.map((it) =>
              it.key === key ? { ...it, state: "done" as const } : it,
            ),
          );
          setDemoDocs((prev) => [
            {
              id: newId("demo"),
              title: file.name,
              ext: file.name.split(".").pop()?.toLowerCase() ?? "txt",
              status: "completed",
              roles: ["admin", "manager", "employee"],
              uploadedAt: Date.now(),
            },
            ...prev,
          ]);
        }, 1800);
        return;
      }

      // 真实上传
      setQueue((q) => [
        ...q,
        { key: `${key}#${file.name}`, name: file.name, size: file.size, state: "uploading" },
      ]);
      (async () => {
        const queueKey = `${key}#${file.name}`;
        try {
          const res = await uploadDocument(file);
          setQueue((q) =>
            q.map((it) =>
              it.key === queueKey ? { ...it, key: res.document_id, state: "parsing" } : it,
            ),
          );
          void pollStatus(res.document_id);
          void refreshList();
        } catch (e) {
          setQueue((q) =>
            q.map((it) =>
              it.key === queueKey
                ? {
                    ...it,
                    state: "failed",
                    message: e instanceof Error ? e.message : "上传失败",
                  }
                : it,
            ),
          );
        }
      })();
    },
    [demo, pollStatus, refreshList],
  );

  async function handleDelete(doc: DocumentMeta) {
    try {
      await deleteDocument(doc.id);
    } catch (e) {
      setListError(e instanceof Error ? e.message : "删除失败");
    }
    setPendingDeleteId(null);
    void refreshList();
  }

  async function handleReingest(doc: DocumentMeta) {
    try {
      await reingestDocument(doc.id);
      void pollStatus(doc.id);
      void refreshList();
    } catch (e) {
      setListError(e instanceof Error ? e.message : "重新解析失败");
    }
  }

  async function pollBatch(ids: string[]) {
    for (let i = 0; i < POLL_MAX; i++) {
      await sleep(POLL_INTERVAL);
      try {
        const docs = await listDocuments();
        setRealDocs(docs);
        const still = docs.filter(
          (d) => ids.includes(d.id) && (d.status === "processing" || d.status === "pending"),
        );
        if (still.length === 0) break;
      } catch {
        // 网络抖动继续轮询
      }
    }
  }

  async function handleReingestAll() {
    if (
      !window.confirm(
        "将用当前 embedding 配置（设置页所选，默认 Ollama bge-m3）重新向量化全部已有文档，旧向量会被覆盖。确认继续？",
      )
    ) {
      return;
    }
    setBatching(true);
    setBatchMsg("");
    try {
      const res = await reingestAllDocuments();
      setBatchMsg(
        `已提交 ${res.enqueued_count} 篇重新摄入` +
          (res.skipped_count ? `，跳过 ${res.skipped_count} 篇（原始文件缺失）` : "") +
          "。",
      );
      void refreshList();
      void pollBatch(res.enqueued.map((e) => e.document_id));
    } catch (e) {
      setBatchMsg(e instanceof Error ? e.message : "批量重新摄入失败");
    } finally {
      setBatching(false);
    }
  }

  const docs = demo ? demoDocs : realDocs;
  const counts = useMemo(
    () => ({
      all: docs.length,
      processing: docs.filter(
        (d) => d.status === "processing" || d.status === "pending",
      ).length,
      completed: docs.filter((d) => d.status === "completed").length,
      failed: docs.filter((d) => d.status === "failed").length,
    }),
    [docs],
  );
  const filtered = docs.filter((d) => {
    if (filter === "all") return true;
    if (filter === "processing")
      return d.status === "processing" || d.status === "pending";
    return d.status === filter;
  });

  return (
    <div className="mx-auto h-full w-full max-w-5xl overflow-y-auto">
      <PageHeader
        title="知识库"
        description={
          demo
            ? "演示环境：上传与列表均为模拟流程。"
            : "上传的文档经解析、切块、向量化后进入检索范围。"
        }
        actions={demo ? <PreviewTag label="演示数据" /> : undefined}
      />

      {listError && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-seal/30 bg-seal-wash px-4 py-3 text-[13px] leading-5 text-seal-deep"
        >
          {listError}
        </p>
      )}

      <UploadZone
        demo={demo}
        onFileQueued={handleFileQueued}
        onDismiss={(key) => setQueue((q) => q.filter((it) => it.key !== key))}
      />
      <QueueList
        items={queue}
        onDismiss={(key) => setQueue((q) => q.filter((it) => it.key !== key))}
      />

      {/* 列表 */}
      <div className="mt-8">
        <div
          className="mb-3 flex items-center justify-between gap-3"
          role="tablist"
          aria-label="按状态筛选"
        >
          <div className="flex items-center gap-1.5">
          {(
            [
              ["all", "全部"],
              ["processing", "进行中"],
              ["completed", "已完成"],
              ["failed", "失败"],
            ] as Array<[Filter, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={filter === key}
              onClick={() => setFilter(key)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                filter === key
                  ? "border-indigo bg-indigo-wash font-medium text-indigo-deep"
                  : "border-line bg-paper text-ink-soft hover:text-ink",
              )}
            >
              {label}
              <span className="ml-1 font-mono text-[10px] opacity-60">
                {counts[key]}
              </span>
            </button>
          ))}
          </div>
          {!demo && (
            <button
              onClick={() => void handleReingestAll()}
              disabled={batching}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                batching
                  ? "cursor-not-allowed border-line bg-porcelain text-ink-faint"
                  : "border-indigo bg-indigo-wash text-indigo-deep hover:bg-indigo/10",
              )}
            >
              <RefreshCw size={12} className={batching ? "animate-spin" : ""} />
              {batching ? "重新摄入中…" : "全部重新摄入"}
            </button>
          )}
        </div>

        {batchMsg && (
          <p
            role="status"
            className="mb-3 rounded-lg border border-indigo/30 bg-indigo-wash px-4 py-2.5 text-[13px] leading-5 text-indigo-deep"
          >
            {batchMsg}
          </p>
        )}

        {filtered.length === 0 ? (
          <EmptyState
            icon={<LibraryBig size={20} />}
            title={filter === "all" ? "还没有文档" : "该状态下没有文档"}
            hint={
              demo
                ? "演示模式下可用上方上传区模拟接入流程。"
                : "上传第一份文档后，它会出现在这里；解析完成后即可在问答中检索到。"
            }
          />
        ) : (
          <div className="overflow-x-auto rounded-xl border border-line bg-paper">
            <table className="w-full min-w-[680px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-xs text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">文档</th>
                  <th className="px-4 py-2.5 font-medium">可见范围</th>
                  <th className="px-4 py-2.5 font-medium">上传时间</th>
                  <th className="px-4 py-2.5 text-right font-medium">块数</th>
                  <th className="px-4 py-2.5 font-medium">状态</th>
                  <th className="px-4 py-2.5 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {filtered.map((d) => (
                  <tr
                    key={d.id}
                    className={cn(
                      "transition-colors hover:bg-porcelain/60",
                      d.status === "failed" && "bg-seal-wash/40",
                    )}
                  >
                    <td className="max-w-64 px-4 py-3">
                      <p className="truncate font-medium text-ink" title={d.title}>
                        {d.title}
                      </p>
                      <p className="mt-0.5 flex items-center gap-2 font-mono text-[11px] text-ink-faint">
                        <span className="uppercase">{d.ext}</span>
                        {d.sizeLabel && <span>{d.sizeLabel}</span>}
                        {d.errorMessage && (
                          <span className="font-sans text-seal">
                            {d.errorMessage}
                          </span>
                        )}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {d.roles.map((r) => (
                          <Badge key={r}>{ROLE_LABELS[r]}</Badge>
                        ))}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-soft">
                      <Time ms={d.uploadedAt} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-ink-soft">
                      {d.chunkCount ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={d.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <IconAction
                          label="重新解析"
                          disabled={d.status === "processing" || d.status === "pending"}
                          onClick={() => void handleReingest(d)}
                        >
                          <RotateCcw size={13} />
                        </IconAction>
                        <IconAction
                          label="删除"
                          pending={pendingDeleteId === d.id}
                          onPendingChange={(on) => setPendingDeleteId(on ? d.id : null)}
                          onConfirm={() => void handleDelete(d)}
                        >
                          <Trash2 size={13} />
                        </IconAction>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function IconAction({
  label,
  onClick,
  pending,
  onPendingChange,
  onConfirm,
  disabled,
  children,
}: {
  label: string;
  onClick?: () => void;
  /** 两步确认：pending=true 表示等待二次确认 */
  pending?: boolean;
  onPendingChange?: (pending: boolean) => void;
  onConfirm?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  function handleClick() {
    if (pending && onConfirm) {
      onConfirm();
      return;
    }
    if (onPendingChange) {
      onPendingChange(true);
      setTimeout(() => onPendingChange(false), 3000);
      return;
    }
    onClick?.();
  }
  return (
    <button
      onClick={handleClick}
      disabled={disabled}
      title={pending ? `再次点击确认${label}` : label}
      aria-label={pending ? `再次点击确认${label}` : label}
      className={cn(
        "rounded p-1.5 transition-colors",
        pending
          ? "bg-seal text-paper hover:bg-seal-deep"
          : "text-ink-soft hover:bg-porcelain hover:text-ink",
        disabled && "cursor-not-allowed opacity-40 hover:bg-transparent",
      )}
    >
      {children}
    </button>
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
