"use client";

// 知识库页：上传（真实接入 + 状态轮询）与文档列表。
// 真实模式：本机 localStorage 记录上传过的文档（后端暂无列表接口，规划中 GET /documents）；
// 演示模式：展示占位文档集，可模拟接入/删除。

import { useCallback, useEffect, useMemo, useState } from "react";
import { LibraryBig, Trash2, RotateCcw } from "lucide-react";
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
import { fetchDocument, uploadDocument } from "@/lib/api";
import { Time } from "@/components/ui/time";
import type { DocumentMeta } from "@/lib/types";
import { cn, newId, ROLE_LABELS } from "@/lib/utils";

const STORE_KEY = "kp.documents.v1";
const POLL_INTERVAL = 2000;
const POLL_MAX = 60;

type Filter = "all" | "processing" | "completed" | "failed";

function loadDocs(): DocumentMeta[] {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as DocumentMeta[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function DocumentsPage() {
  const { demo } = useDemoMode();
  const [realDocs, setRealDocs] = useState<DocumentMeta[]>([]);
  const [demoDocs, setDemoDocs] = useState<DocumentMeta[]>(demoDocuments);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [filter, setFilter] = useState<Filter>("all");
  // 两步删除确认：首次点击进入待确认态，3 秒未确认自动还原
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  useEffect(() => {
    setRealDocs(loadDocs());
  }, []);

  useEffect(() => {
    if (demo) return;
    window.localStorage.setItem(STORE_KEY, JSON.stringify(realDocs));
  }, [realDocs, demo]);

  // 真实模式：刷新未完成文档的状态（页面打开时各轮询一次）
  useEffect(() => {
    if (demo) return;
    realDocs
      .filter((d) => d.status === "pending" || d.status === "processing")
      .forEach((d) => void pollStatus(d.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [demo]);

  const pollStatus = useCallback(async (docId: string) => {
    for (let i = 0; i < POLL_MAX; i++) {
      await sleep(POLL_INTERVAL);
      try {
        const data = await fetchDocument(docId);
        setRealDocs((prev) =>
          prev.map((d) =>
            d.id === docId
              ? {
                  ...d,
                  status: data.status,
                  errorMessage: data.error_message,
                }
              : d,
          ),
        );
        if (data.status === "completed" || data.status === "failed") return;
      } catch {
        // 网络抖动继续轮询
      }
    }
  }, []);

  const handleFileQueued = useCallback(
    (file: File, key: string, rejected: boolean) => {
      if (rejected) {
        setQueue((q) => [
          ...q,
          { key, name: file.name, size: file.size, state: "rejected" },
        ]);
        return;
      }
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "txt";
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
              ext,
              status: "completed",
              roles: ["admin", "manager", "employee"],
              uploadedAt: Date.now(),
              sizeLabel: undefined,
            },
            ...prev,
          ]);
        }, 1800);
        return;
      }

      // 真实上传
      setQueue((q) => [
        ...q,
        { key, name: file.name, size: file.size, state: "uploading" },
      ]);
      (async () => {
        try {
          const res = await uploadDocument(file);
          setQueue((q) =>
            q.map((it) =>
              it.key === key ? { ...it, state: "parsing" } : it,
            ),
          );
          setRealDocs((prev) => [
            {
              id: res.document_id,
              title: file.name,
              ext,
              status: "pending",
              roles: ["admin", "manager", "employee"],
              uploadedAt: Date.now(),
            },
            ...prev,
          ]);
          void pollStatus(res.document_id);
        } catch (e) {
          setQueue((q) =>
            q.map((it) =>
              it.key === key
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
    [demo, pollStatus],
  );

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
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader
        title="知识库"
        description={
          <>
            上传的文档经解析、切块、向量化后进入检索范围。
            {!demo && " 已上传列表保存在本机浏览器。"}
          </>
        }
        actions={demo ? <PreviewTag label="演示数据" /> : undefined}
      />

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
        <div className="mb-3 flex items-center gap-1.5" role="tablist" aria-label="按状态筛选">
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
            <table className="w-full min-w-[640px] text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-xs text-ink-faint">
                  <th className="px-4 py-2.5 font-medium">文档</th>
                  <th className="px-4 py-2.5 font-medium">可见范围</th>
                  <th className="px-4 py-2.5 font-medium">上传时间</th>
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
                    <td className="px-4 py-3">
                      <StatusBadge status={d.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {demo ? (
                          <>
                            <IconAction
                              label="重新解析（演示）"
                              onClick={() => {
                                setDemoDocs((prev) =>
                                  prev.map((x) =>
                                    x.id === d.id
                                      ? { ...x, status: "processing", errorMessage: null }
                                      : x,
                                  ),
                                );
                                setTimeout(() => {
                                  setDemoDocs((prev) =>
                                    prev.map((x) =>
                                      x.id === d.id
                                        ? { ...x, status: "completed" }
                                        : x,
                                    ),
                                  );
                                }, 2000);
                              }}
                            >
                              <RotateCcw size={13} />
                            </IconAction>
                            <IconAction
                              label="删除（演示）"
                              pending={pendingDeleteId === d.id}
                              onPendingChange={(on) =>
                                setPendingDeleteId(on ? d.id : null)
                              }
                              onConfirm={() => {
                                setDemoDocs((prev) =>
                                  prev.filter((x) => x.id !== d.id),
                                );
                                setPendingDeleteId(null);
                              }}
                            >
                              <Trash2 size={13} />
                            </IconAction>
                          </>
                        ) : (
                          <span
                            className="cursor-help pr-1 text-[11px] text-ink-faint"
                            title="删除/重传接口规划中（DELETE /documents/{id}）；当前可在本机移除记录后重新上传"
                          >
                            接口规划中
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!demo && realDocs.length > 0 && (
          <p className="mt-3 text-[11px] leading-4 text-ink-faint">
            权限列当前展示后端默认值（全角色可见）。文档级可见范围设置与管理接口规划中。
          </p>
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
  children,
}: {
  label: string;
  onClick?: () => void;
  /** 两步确认：pending=true 表示等待二次确认 */
  pending?: boolean;
  onPendingChange?: (pending: boolean) => void;
  onConfirm?: () => void;
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
      title={pending ? "再次点击确认删除" : label}
      aria-label={pending ? "再次点击确认删除" : label}
      className={cn(
        "rounded p-1.5 transition-colors",
        pending
          ? "bg-seal text-paper hover:bg-seal-deep"
          : "text-ink-soft hover:bg-porcelain hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
