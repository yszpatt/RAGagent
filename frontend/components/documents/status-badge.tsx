"use client";

import { Badge } from "@/components/ui/badge";
import { STATUS_LABELS } from "@/lib/utils";
import type { DocStatus } from "@/lib/types";

export function StatusBadge({ status }: { status: DocStatus }) {
  if (status === "completed") return <Badge tone="jade">✓ {STATUS_LABELS[status]}</Badge>;
  if (status === "failed") return <Badge tone="seal">✕ {STATUS_LABELS[status]}</Badge>;
  if (status === "processing" || status === "pending")
    return (
      <Badge tone="amber">
        <span
          className="inline-block size-1.5 animate-pulse rounded-full bg-amber motion-reduce:animate-none"
          aria-hidden="true"
        />
        {STATUS_LABELS[status]}
      </Badge>
    );
  return <Badge>{status}</Badge>;
}
