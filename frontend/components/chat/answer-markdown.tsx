"use client";

// 答案渲染：Markdown + 行内引用标记 [n] → 朱砂引用牌（可点击打开来源案卷）。
// 实现方式：把 [n] 预转换为 markdown 链接 [n](#ref-n)，再在 <a> 渲染层替换为引用牌。

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn, refLabel } from "@/lib/utils";

export function prepareAnswer(md: string): string {
  return md.replace(/\[(\d+)\](?!\()/g, "[$1](#ref-$1)");
}

function CitationMark({
  n,
  onCitation,
}: {
  n: number;
  onCitation?: (n: number) => void;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onCitation?.(n);
      }}
      title={`查看来源 ${refLabel(n - 1)}`}
      className="mx-0.5 inline-flex h-4 min-w-4 translate-y-[-2px] cursor-pointer items-center justify-center rounded-[3px] border border-seal/50 bg-seal-wash px-0.5 align-middle font-mono text-[10px] leading-3 text-seal transition-colors hover:bg-seal hover:text-paper"
    >
      {n}
    </button>
  );
}

export function AnswerMarkdown({
  text,
  onCitation,
  className,
}: {
  text: string;
  onCitation?: (n: number) => void;
  className?: string;
}) {
  return (
    <div className={cn("text-[13.5px] leading-6 text-ink", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ node, children, href, ...props }) => {
            void node;
            const m = typeof href === "string" && href.match(/^#ref-(\d+)$/);
            if (m) {
              return <CitationMark n={Number(m[1])} onCitation={onCitation} />;
            }
            return (
              <a href={href} {...props} className="text-indigo underline underline-offset-2">
                {children}
              </a>
            );
          },
          ol: ({ children }) => (
            <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-ink-faint">
              {children}
            </ol>
          ),
          ul: ({ children }) => (
            <ul className="my-2 list-disc space-y-1 pl-5 marker:text-ink-faint">
              {children}
            </ul>
          ),
          p: ({ children }) => <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-semibold text-ink">{children}</strong>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-line bg-porcelain px-2 py-1 text-left font-medium">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-line px-2 py-1">{children}</td>
          ),
          code: ({ children }) => (
            <code className="rounded bg-porcelain px-1 py-0.5 font-mono text-xs">
              {children}
            </code>
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-2 border-l-2 border-line-strong pl-3 text-ink-soft">
              {children}
            </blockquote>
          ),
        }}
      >
        {prepareAnswer(text)}
      </ReactMarkdown>
    </div>
  );
}
