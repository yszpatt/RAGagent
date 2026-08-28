"use client";

// 来源案卷查看器：展示单条引用的原文摘录（演示）或元数据（真实引用，后端内容接口待接入）。

import { FileText } from "lucide-react";
import { Drawer } from "@/components/ui/drawer";
import { Badge } from "@/components/ui/badge";
import type { SourceRef } from "@/lib/types";

export function SourceDrawer({
  source,
  onClose,
  demo,
}: {
  source: SourceRef | null;
  onClose: () => void;
  demo: boolean;
}) {
  return (
    <Drawer
      open={source !== null}
      onClose={onClose}
      title={
        <span className="flex items-center gap-2">
          <span className="rounded-[3px] border border-seal/50 bg-seal-wash px-1.5 py-0.5 font-mono text-xs text-seal">
            {source?.ref ?? ""}
          </span>
          来源案卷
          {demo && <Badge tone="seal">演示</Badge>}
        </span>
      }
      subtitle={source?.title}
    >
      {source && (
        <div className="flex flex-col gap-4">
          <dl className="grid grid-cols-[64px_1fr] gap-x-3 gap-y-2 text-xs">
            <dt className="text-ink-faint">文档</dt>
            <dd className="flex items-center gap-1.5 text-ink">
              <FileText size={13} className="text-ink-faint" />
              {source.title}
            </dd>
            <dt className="text-ink-faint">页码</dt>
            <dd className="font-mono text-ink">
              {source.page != null ? `第 ${source.page} 页` : "—"}
            </dd>
            {source.section && (
              <>
                <dt className="text-ink-faint">章节</dt>
                <dd className="text-ink">{source.section}</dd>
              </>
            )}
          </dl>

          {source.excerpt ? (
            <figure className="relative rounded-lg border border-line bg-porcelain p-4">
              <blockquote className="whitespace-pre-wrap text-[13px] leading-6 text-ink">
                {source.excerpt}
              </blockquote>
              <span
                aria-hidden="true"
                className="pointer-events-none absolute -top-2.5 right-4 -rotate-6 rounded-[3px] border-2 border-seal/60 bg-paper px-1.5 py-0.5 font-display text-xs font-bold tracking-widest text-seal/80"
              >
                已核实
              </span>
            </figure>
          ) : (
            <div className="rounded-lg border border-dashed border-line-strong bg-porcelain p-4 text-xs leading-5 text-ink-soft">
              原文摘录暂不可展示：后端尚未提供引用内容查询接口
              （规划中 <code className="font-mono">GET /chat/&#123;id&#125;/citations</code>）。
              当前可核对的信息：文档名与页码。
            </div>
          )}

          {source.chunkId && (
            <p className="font-mono text-[11px] text-ink-faint">
              chunk_id: {source.chunkId}
            </p>
          )}
        </div>
      )}
    </Drawer>
  );
}
