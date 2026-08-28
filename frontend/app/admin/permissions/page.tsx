"use client";

// 权限管理：文档 × 角色的可见范围矩阵。
// 真实模式：列表来自 GET /documents，变更 PUT /documents/{id}/permissions（管理员强制保留）；
// 演示模式：占位数据本地交互，不保存。

import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/ui/page";
import { Badge, PreviewTag } from "@/components/ui/badge";
import { useDemoMode } from "@/lib/demo-context";
import { permissionRows } from "@/lib/demo-data";
import { listDocuments, updateDocumentPermissions } from "@/lib/api";
import { cn, ROLE_LABELS } from "@/lib/utils";
import type { Role } from "@/lib/types";

const ROLES: Role[] = ["admin", "manager", "employee"];

type Matrix = Record<string, Set<Role>>;

function Toggle({
  checked,
  disabled,
  label,
  onChange,
  saving,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  onChange: () => void;
  saving?: boolean;
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled || saving}
      onClick={onChange}
      className={cn(
        "relative h-5 w-9 rounded-full border transition-colors",
        checked ? "border-indigo bg-indigo" : "border-line-strong bg-porcelain",
        (disabled || saving) && "cursor-not-allowed opacity-70",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 size-3.5 rounded-full bg-paper shadow transition-all",
          checked ? "left-[18px]" : "left-0.5 bg-ink-faint",
        )}
      />
    </button>
  );
}

export default function PermissionsPage() {
  const { demo } = useDemoMode();
  const [matrix, setMatrix] = useState<Matrix>(() => {
    const init: Matrix = {};
    permissionRows.forEach((row) => {
      init[row.id] = new Set(row.roles);
    });
    return init;
  });
  const [rows, setRows] = useState<Array<{ id: string; title: string }>>(
    permissionRows.map(({ id, title }) => ({ id, title })),
  );
  const [savingId, setSavingId] = useState<string | null>(null);
  const [error, setError] = useState("");

  // 真实模式：加载后端文档列表（角色为真实值）
  useEffect(() => {
    if (demo) return;
    listDocuments()
      .then((docs) => {
        const init: Matrix = {};
        docs.forEach((d) => init[d.id] = new Set(d.roles));
        setMatrix(init);
        setRows(docs.map((d) => ({ id: d.id, title: d.title })));
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "获取文档列表失败"),
      );
  }, [demo]);

  const toggle = useCallback(
    (docId: string, role: Role) => {
      if (role === "admin") return; // 管理员始终可见
      const next = new Set(matrix[docId]);
      if (next.has(role)) next.delete(role);
      else next.add(role);

      if (demo) {
        setMatrix((prev) => ({ ...prev, [docId]: next }));
        return;
      }
      // 真实模式：乐观更新，PUT 失败回滚
      const prevRoles = matrix[docId];
      setMatrix((m) => ({ ...m, [docId]: next }));
      setSavingId(docId);
      updateDocumentPermissions(docId, [...next])
        .then((saved) => {
          setMatrix((m) => ({ ...m, [docId]: new Set(saved) }));
          setError("");
        })
        .catch((e) => {
          setMatrix((m) => ({ ...m, [docId]: prevRoles }));
          setError(e instanceof Error ? e.message : "保存失败");
        })
        .finally(() => setSavingId(null));
    },
    [demo, matrix],
  );

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader
        title="权限管理"
        description="按文档设置角色可见范围。权限过滤发生在检索之前（SQL WHERE），未授权文档不参与召回，从根上杜绝越权泄漏。"
        actions={demo ? <PreviewTag label="演示" /> : undefined}
      />

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-seal/30 bg-seal-wash px-4 py-3 text-[13px] leading-5 text-seal-deep"
        >
          {error}
        </p>
      )}

      <div className="mb-4 flex items-start gap-2.5 rounded-lg border border-amber/30 bg-amber-wash px-4 py-3 text-xs leading-5 text-ink">
        <ShieldCheck size={15} className="mt-0.5 shrink-0 text-amber" />
        {demo ? (
          <p>
            当前为交互预览：勾选即时生效于页面，但<strong>不会保存</strong>。
            管理员列固定勾选——按「新文档默认全角色可见，可在此收窄」的策略设计。
          </p>
        ) : (
          <p>
            变更即时保存到后端（检索时实时读取，不走缓存）。
            管理员列固定可见：按最小权限模型的底线设计，不可关闭。
          </p>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-line-strong bg-paper px-6 py-14 text-center text-sm text-ink-soft">
          还没有文档——先到「知识库」上传，再回来配置可见范围。
        </div>
      ) : (
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
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-porcelain/60">
                  <td className="max-w-72 px-4 py-3">
                    <p className="truncate font-medium text-ink" title={row.title}>
                      {row.title}
                    </p>
                  </td>
                  {ROLES.map((role) => (
                    <td key={role} className="px-4 py-3 text-center">
                      <Toggle
                        checked={matrix[row.id]?.has(role) ?? false}
                        disabled={role === "admin"}
                        saving={savingId === row.id && role !== "admin"}
                        label={`${row.title} 对${ROLE_LABELS[role]}可见`}
                        onChange={() => toggle(row.id, role)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-ink-soft">
        <Badge tone="indigo">检索前过滤</Badge>
        <span>
          角色集合在查询时实时读取，权限变更即时生效——见设计文档 §5.2。
        </span>
      </div>
    </div>
  );
}
