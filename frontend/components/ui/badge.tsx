// 徽章：状态 / 角色 / 「演示」「预览」标记。
// 颜色语义：jade=完成，amber=进行中，seal=失败与需核验标记，indigo=信息。

import { cn } from "@/lib/utils";

type Tone = "jade" | "amber" | "seal" | "indigo" | "neutral";

const toneClasses: Record<Tone, string> = {
  jade: "bg-jade-wash text-jade border-jade/25",
  amber: "bg-amber-wash text-amber border-amber/25",
  seal: "bg-seal-wash text-seal border-seal/25",
  indigo: "bg-indigo-wash text-indigo border-indigo/25",
  neutral: "bg-porcelain text-ink-soft border-line",
};

export function Badge({
  tone = "neutral",
  className,
  children,
}: {
  tone?: Tone;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs leading-4",
        toneClasses[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** 「演示数据 / 预览」标记——朱砂，提示当前内容非真实数据 */
export function PreviewTag({ label = "演示" }: { label?: string }) {
  return (
    <span
      title="当前展示为占位数据，正式功能接入后替换"
      className="inline-flex cursor-help items-center rounded-sm border border-seal/40 px-1 py-px font-mono text-[10px] leading-3.5 text-seal"
    >
      {label}
    </span>
  );
}
