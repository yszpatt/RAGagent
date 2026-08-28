"use client";

// 审计日志（预览）：谁、在什么时候、问了什么、命中多少引用。
// 演示数据；对应规划接口 GET /admin/audit-logs（分页 + 按用户/时间/关键词过滤）。

import { useMemo, useState } from "react";
import { ScrollText, Search } from "lucide-react";
import { PageHeader, EmptyState } from "@/components/ui/page";
import { Badge, PreviewTag } from "@/components/ui/badge";
import { Time } from "@/components/ui/time";
import { demoAudit, type AuditEntry } from "@/lib/demo-data";
import { cn } from "@/lib/utils";

const ACTION_TONE: Record<AuditEntry["action"], "indigo" | "jade" | "seal" | "neutral"> = {
  查询: "indigo",
  上传: "jade",
  权限变更: "neutral",
  无答案: "seal",
};

export default function AuditPage() {
  const [keyword, setKeyword] = useState("");
  const [action, setAction] = useState<"全部" | AuditEntry["action"]>("全部");

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return demoAudit.filter((e) => {
      if (action !== "全部" && e.action !== action) return false;
      if (!kw) return true;
      return (
        e.detail.toLowerCase().includes(kw) ||
        e.actor.toLowerCase().includes(kw)
      );
    });
  }, [keyword, action]);

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader
        title="审计日志"
        description="query / upload / permission_change 三类关键动作全量留痕，满足合规追溯要求。"
        actions={<PreviewTag label="演示数据" />}
      />

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
        {(["全部", "查询", "上传", "权限变更", "无答案"] as const).map((a) => (
          <button
            key={a}
            onClick={() => setAction(a)}
            aria-pressed={action === a}
            className={cn(
              "rounded-full border px-3 py-1 text-xs transition-colors",
              action === a
                ? "border-indigo bg-indigo-wash font-medium text-indigo-deep"
                : "border-line bg-paper text-ink-soft hover:text-ink",
            )}
          >
            {a}
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
          hint="换个关键词，或清除筛选条件。"
          action={
            <button
              onClick={() => {
                setKeyword("");
                setAction("全部");
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
              {filtered.map((e, i) => (
                <tr key={i} className="hover:bg-porcelain/60">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-ink-soft">
                    <Time ms={e.at} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className="text-ink">{e.actor}</span>
                    <span className="ml-1.5 text-[11px] text-ink-faint">
                      {e.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone={ACTION_TONE[e.action]}>{e.action}</Badge>
                  </td>
                  <td className="max-w-80 truncate px-4 py-3 text-ink" title={e.detail}>
                    {e.detail}
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

      <p className="mt-4 rounded-lg border border-dashed border-line-strong bg-paper px-4 py-3 text-xs leading-5 text-ink-soft">
        本页为规划功能预览。数据库中 <code className="font-mono">audit_logs</code>{" "}
        表与索引已就绪，待后端在 query / upload / permission_change 链路埋点并开放{" "}
        <code className="font-mono">/admin/audit-logs</code> 后切换为真实数据。
      </p>
    </div>
  );
}
