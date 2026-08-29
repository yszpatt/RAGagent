"use client";

// 审计日志：谁、在什么时候、问了什么/做了什么、命中多少引用。
// 真实模式：GET /admin/audit-logs；演示模式：占位数据。

import { useEffect, useMemo, useState } from "react";
import { ScrollText, Search } from "lucide-react";
import { PageHeader, EmptyState } from "@/components/ui/page";
import { Badge, PreviewTag } from "@/components/ui/badge";
import { Time } from "@/components/ui/time";
import { useDemoMode } from "@/lib/demo-context";
import { demoAudit, type AuditEntry } from "@/lib/demo-data";
import { fetchAuditLogs, type AuditRow } from "@/lib/api";
import { cn } from "@/lib/utils";

/** 后端动作 → 展示标签 / 徽章色调 */
const ACTION_META: Record<string, { label: string; tone: "indigo" | "jade" | "seal" | "neutral" }> = {
  query: { label: "查询", tone: "indigo" },
  upload: { label: "上传", tone: "jade" },
  permission_change: { label: "权限变更", tone: "neutral" },
  delete: { label: "删除", tone: "seal" },
};

const FILTERS = ["全部", "查询", "上传", "权限变更", "删除"] as const;
const FILTER_TO_ACTION: Record<(typeof FILTERS)[number], string | undefined> = {
  "全部": undefined,
  "查询": "query",
  "上传": "upload",
  "权限变更": "permission_change",
  "删除": "delete",
};

interface Row {
  key: string;
  at: number;
  actor: string;
  actorRole: string | null;
  action: string;
  actionLabel: string;
  tone: "indigo" | "jade" | "seal" | "neutral";
  detail: string;
  hitCount: number | null;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "管理员",
  manager: "经理",
  employee: "员工",
};

function fromBackend(rows: AuditRow[]): Row[] {
  return rows.map((r) => {
    const meta = ACTION_META[r.action] ?? { label: r.action, tone: "neutral" as const };
    return {
      key: r.id,
      at: Date.parse(r.created_at) || 0,
      actor: r.actor,
      actorRole: r.actor_role ? ROLE_LABELS[r.actor_role] ?? r.actor_role : null,
      action: r.action,
      actionLabel: meta.label,
      tone: meta.tone,
      detail: r.query_text ?? "",
      hitCount: r.hit_count,
    };
  });
}

function fromDemo(rows: AuditEntry[]): Row[] {
  return rows.map((e, i) => ({
    key: `demo-${i}`,
    at: e.at,
    actor: e.actor,
    actorRole: e.role,
    action: e.action,
    actionLabel: e.action,
    tone: e.action === "查询" ? "indigo" : e.action === "上传" ? "jade" : e.action === "无答案" ? "seal" : "neutral",
    detail: e.detail,
    hitCount: e.hitCount,
  }));
}

export default function AuditPage() {
  const { demo } = useDemoMode();
  const [keyword, setKeyword] = useState("");
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("全部");
  const [realRows, setRealRows] = useState<Row[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (demo) return;
    fetchAuditLogs({ limit: 200 })
      .then((rows) => {
        setRealRows(fromBackend(rows));
        setError("");
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "获取审计日志失败"),
      );
  }, [demo]);

  const rows = demo ? fromDemo(demoAudit) : realRows;

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    const actionKey = FILTER_TO_ACTION[filter];
    return rows.filter((e) => {
      if (actionKey && e.action !== actionKey) return false;
      if (!kw) return true;
      return e.detail.toLowerCase().includes(kw) || e.actor.toLowerCase().includes(kw);
    });
  }, [rows, keyword, filter]);

  return (
    <div className="mx-auto h-full w-full max-w-5xl overflow-y-auto">
      <PageHeader
        title="审计日志"
        description="query / upload / permission_change / delete 关键动作全量留痕，满足合规追溯要求。"
        actions={demo ? <PreviewTag label="演示数据" /> : undefined}
      />

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-seal/30 bg-seal-wash px-4 py-3 text-[13px] leading-5 text-seal-deep"
        >
          {error}
        </p>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="relative">
          <Search
            size={14}
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint"
          />
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            aria-label="搜索审计日志"
            placeholder="搜索问题或操作人…"
            className="w-64 rounded-lg border border-line bg-paper py-1.5 pl-8 pr-3 text-[13px] text-ink placeholder:text-ink-faint focus:border-indigo/50 focus:outline-none"
          />
        </label>
        {FILTERS.map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={cn(
              "rounded-full border px-3 py-1 text-xs transition-colors",
              filter === f
                ? "border-indigo bg-indigo-wash font-medium text-indigo-deep"
                : "border-line bg-paper text-ink-soft hover:text-ink",
            )}
          >
            {f}
          </button>
        ))}
        <span className="ml-auto font-mono text-[11px] text-ink-faint">
          {filtered.length} 条
        </span>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={<ScrollText size={20} />}
          title="没有匹配的记录"
          hint={
            demo
              ? "换个关键词，或清除筛选条件。"
              : "有一次问答或上传操作后，这里就会出现记录。"
          }
          action={
            <button
              onClick={() => {
                setKeyword("");
                setFilter("全部");
              }}
              className="rounded-md border border-line bg-paper px-3 py-1.5 text-xs text-ink-soft hover:text-ink"
            >
              清除筛选
            </button>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-line bg-paper">
          <table className="w-full min-w-[680px] text-left text-[13px]">
            <thead>
              <tr className="border-b border-line text-xs text-ink-faint">
                <th className="px-4 py-2.5 font-medium">时间</th>
                <th className="px-4 py-2.5 font-medium">操作人</th>
                <th className="px-4 py-2.5 font-medium">动作</th>
                <th className="px-4 py-2.5 font-medium">内容</th>
                <th className="px-4 py-2.5 text-right font-medium">命中引用</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {filtered.map((e) => (
                <tr key={e.key} className="hover:bg-porcelain/60">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-soft">
                    <Time ms={e.at} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="text-ink">{e.actor}</span>
                    {e.actorRole && (
                      <span className="ml-1.5 text-[11px] text-ink-faint">
                        {e.actorRole}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={e.tone}>{e.actionLabel}</Badge>
                  </td>
                  <td className="max-w-80 truncate px-4 py-3 text-ink" title={e.detail}>
                    {e.detail || "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right font-mono text-xs text-ink-soft">
                    {e.hitCount ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {demo && (
        <p className="mt-4 rounded-lg border border-dashed border-line-strong bg-paper px-4 py-3 text-xs leading-5 text-ink-soft">
          本页为规划功能预览：后端埋点与 <code className="font-mono">/admin/audit-logs</code>{" "}
          接口已就绪，接入后端即可查看真实审计记录。
        </p>
      )}
    </div>
  );
}
