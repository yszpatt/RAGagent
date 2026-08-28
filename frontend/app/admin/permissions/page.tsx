"use client";

// 权限管理（预览）：文档 × 角色的可见范围矩阵。
// 演示数据 + 本地可交互（不保存）；对应规划接口 POST /admin/documents/{id}/permissions。

import { useState } from "react";
import { ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/ui/page";
import { Badge, PreviewTag } from "@/components/ui/badge";
import { permissionRows } from "@/lib/demo-data";
import { cn, ROLE_LABELS } from "@/lib/utils";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["admin", "manager", "employee"];

export default function PermissionsPage() {
  // 本地交互态：勾选立即生效于视图，但不持久化（预览环境）
  const [matrix, setMatrix] = useState<Record<string, Set<Role>>>(() => {
    const init: Record<string, Set<Role>> = {};
    permissionRows.forEach((row) => {
      init[row.id] = new Set(row.roles);
    });
    return init;
  });

  function toggle(docId: string, role: Role) {
    setMatrix((prev) => {
      const next = new Set(prev[docId]);
      // 管理员始终可见（最小权限模型的底线）
      if (role === "admin") return prev;
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return { ...prev, [docId]: next };
    });
  }

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader
        title="权限管理"
        description="按文档设置角色可见范围。权限过滤发生在检索之前（SQL WHERE），未授权文档不参与召回，从根上杜绝越权泄漏。"
        actions={<PreviewTag label="预览" />}
      />

      <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-amber/30 bg-amber-wash px-4 py-3 text-xs leading-5 text-ink">
        <ShieldCheck size={15} className="mt-0.5 shrink-0 text-amber" />
        <p>
          当前为交互预览：勾选即时生效于页面，但<strong>不会保存</strong>。
          管理员列固定勾选——按「新文档默认仅管理员可见，管理员手动放开」的默认安全策略设计，
          待后端权限接口接入后启用保存。
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-paper">
        <table className="w-full min-w-[560px] text-left text-[13px]">
          <thead>
            <tr className="border-b border-line text-xs text-ink-faint">
              <th className="px-4 py-2.5 font-medium">文档</th>
              {ROLES.map((r) => (
                <th key={r} className="px-4 py-2.5 text-center font-medium">
                  {ROLE_LABELS[r]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {permissionRows.map((row) => (
              <tr key={row.id} className="hover:bg-porcelain/60">
                <td className="max-w-72 px-4 py-3">
                  <p className="truncate font-medium text-ink" title={row.title}>
                    {row.title}
                  </p>
                  <p className="mt-0.5 font-mono text-[11px] text-ink-faint">
                    {row.id}
                  </p>
                </td>
                {ROLES.map((role) => {
                  const checked = matrix[row.id]?.has(role) ?? false;
                  return (
                    <td key={role} className="px-4 py-3 text-center">
                      <button
                        role="switch"
                        aria-checked={checked}
                        aria-label={`${row.title} 对${ROLE_LABELS[role]}可见`}
                        disabled={role === "admin"}
                        onClick={() => toggle(row.id, role)}
                        className={cn(
                          "relative h-5 w-9 rounded-full border transition-colors",
                          checked
                            ? "border-indigo bg-indigo"
                            : "border-line-strong bg-porcelain",
                          role === "admin" ? "cursor-not-allowed opacity-80" : "",
                        )}
                      >
                        <span
                          className={cn(
                            "absolute top-0.5 size-3.5 rounded-full bg-paper shadow transition-all",
                            checked ? "left-[18px]" : "left-0.5 bg-ink-faint",
                          )}
                        />
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
        <Badge tone="indigo">检索前过滤</Badge>
        <span>
          角色集合在查询时实时读取，权限变更即时生效（不走缓存）——
          见设计文档 §5.2。
        </span>
      </div>
    </div>
  );
}
