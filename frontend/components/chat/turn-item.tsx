"use client";

// 单轮问答 = 一条卷宗条目：等宽回合编号 + 问 + 答 + 来源行。
// 不用聊天气泡：检索问答是查询日志，编号与眉标承载真实结构信息。

import { AnswerMarkdown } from "./answer-markdown";
import { Badge } from "@/components/ui/badge";
import { Time } from "@/components/ui/time";
import { demoSources } from "@/lib/demo-data";
import { usePrefs } from "@/lib/prefs";
import type { Citation, SourceRef, Turn } from "@/lib/types";
import { cn, refLabel } from "@/lib/utils";

function CitationChip({
  citation,
  label,
  onClick,
}: {
  citation: Citation;
  label: string;
  onClick: () => void;
}) {
  const { t } = usePrefs();
  return (
    <button
      type="button"
      onClick={onClick}
      className="group inline-flex items-center gap-1.5 rounded-[4px] border border-seal/40 bg-seal-wash px-2 py-1 text-xs text-seal transition-colors hover:bg-seal hover:text-paper"
      title={t("chat.viewSources")}
    >
      <span className="font-mono">{label}</span>
      <span className="opacity-70 group-hover:opacity-90">
        {citation.page != null
          ? t("chat.pageNum", { n: citation.page })
          : t("chat.pageUnknown")}
      </span>
    </button>
  );
}

export function TurnItem({
  turn,
  index,
  demo,
  displayAnswer,
  typing,
  onCitation,
}: {
  turn: Turn;
  index: number;
  demo: boolean;
  /** 打字机效果下的当前展示文本；缺省展示全文 */
  displayAnswer?: string;
  typing?: boolean;
  onCitation: (citation: Citation, index: number) => void;
}) {
  const noAnswer = turn.no_answer;
  const { t } = usePrefs();
  return (
    <article
      className={cn(
        "rise rounded-xl border border-line bg-paper px-5 py-4",
        typing && "opacity-95",
      )}
      aria-label={t("chat.roundAria", { n: index + 1 })}
    >
      {/* 问 */}
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-[11px] text-ink-faint">
          {String(index + 1).padStart(3, "0")}
        </span>
        <span className="rounded-sm border border-line bg-porcelain px-1.5 py-px font-mono text-[10px] text-ink-soft">
          {t("chat.q")}
        </span>
        <h2 className="min-w-0 flex-1 text-sm font-medium text-ink">
          {turn.query}
        </h2>
        <Time
          ms={turn.at}
          className="hidden shrink-0 font-mono text-[11px] text-ink-faint sm:block"
        />
      </div>

      <div className="my-3 border-t border-dashed border-line" />

      {/* 答 */}
      <div className="flex items-baseline gap-3">
        <span className="font-mono text-[11px] text-ink-faint" aria-hidden="true">
          {String(index + 1).padStart(3, "0")}
        </span>
        <span className="rounded-sm border border-seal/40 bg-seal-wash px-1.5 py-px font-mono text-[10px] text-seal">
          {t("chat.a")}
        </span>
        {demo && <Badge tone="seal">{t("chat.demoBadge")}</Badge>}
      </div>

      <div className="mt-2 pl-0 sm:pl-9">
        {noAnswer ? (
          <div className="rounded-lg border border-amber/30 bg-amber-wash px-4 py-3 text-[13px] leading-6 text-ink">
            {turn.answer}
            <p className="mt-1 text-xs text-ink-soft">
              {t("chat.noAnswer")}
            </p>
          </div>
        ) : (
          <>
            <AnswerMarkdown
              text={displayAnswer ?? turn.answer}
              onCitation={(n) => {
                const c = turn.citations[n - 1];
                if (c) onCitation(c, n - 1);
              }}
            />
            {typing && (
              <span
                aria-hidden="true"
                className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-seal align-middle motion-reduce:animate-none"
              />
            )}
          </>
        )}

        {!noAnswer && turn.citations.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] tracking-widest text-ink-faint">
              {t("chat.sources")}
            </span>
            {turn.citations.map((c, i) => (
              <CitationChip
                key={c.chunk_id + i}
                citation={c}
                label={refLabel(i)}
                onClick={() => onCitation(c, i)}
              />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

export function sourceFromCitation(
  citation: Citation,
  index: number,
  demo: boolean,
  t: (key: import("@/lib/prefs").DictKey, vars?: Record<string, string | number>) => string,
): SourceRef {
  if (demo) {
    // 演示引用：从案卷库取原文摘录（lib/demo-data.ts）
    const known = demoSources[citation.chunk_id];
    const base: SourceRef = known ?? {
      ref: t("chat.refPrefix") + "00",
      title: t("chat.demoDoc"),
      page: citation.page,
      excerpt: t("chat.demoExcerpt"),
      chunkId: citation.chunk_id,
    };
    return { ...base, ref: refLabel(index) };
  }
  // 真实引用：后端 _enrich_citations 回填标题/节/摘录（缺失时抽屉展示规划说明）
  return {
    ref: refLabel(index),
    title: citation.document_title || t("chat.kbRef"),
    page: citation.page,
    section: citation.section ?? null,
    excerpt: citation.excerpt ?? undefined,
    chunkId: citation.chunk_id,
  };
}
