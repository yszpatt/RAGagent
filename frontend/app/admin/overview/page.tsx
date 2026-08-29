"use client";

// 使用看板：问答量 / 无答案率 / 引用率 / 解析失败率等。
// 真实模式：GET /admin/metrics（采纳率与时延分位待埋点，展示占位说明）；
// 演示模式：占位数据。

import { useEffect, useState } from "react";
import { PageHeader } from "@/components/ui/page";
import { PreviewTag } from "@/components/ui/badge";
import { useDemoMode } from "@/lib/demo-context";
import { demoMetrics } from "@/lib/demo-data";
import { fetchMetrics, type MetricsPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function MetricCard({
  label,
  value,
  unit,
  hint,
  good,
}: {
  label: string;
  value: string | number;
  unit?: string;
  hint?: string;
  good?: boolean;
}) {
  return (
    <div className="rounded-xl border border-line bg-paper px-4 py-3.5">
      <p className="text-xs text-ink-faint">{label}</p>
      <p className="mt-1.5 font-mono text-2xl leading-7 text-ink">
        {value}
        {unit && <span className="ml-0.5 text-sm text-ink-soft">{unit}</span>}
        {good !== undefined && (
          <span
            aria-hidden="true"
            className={cn(
              "ml-2 inline-block size-2 rounded-full align-middle",
              good ? "bg-jade" : "bg-amber",
            )}
          />
        )}
      </p>
      {hint && <p className="mt-1 text-[11px] text-ink-faint">{hint}</p>}
    </div>
  );
}

export default function OverviewPage() {
  const { demo } = useDemoMode();
  const [metrics, setMetrics] = useState<MetricsPayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (demo) return;
    fetchMetrics()
      .then((m) => {
        setMetrics(m);
        setError("");
      })
      .catch((e) =>
        setError(e instanceof Error ? e.message : "获取指标失败"),
      );
  }, [demo]);

  if (demo) {
    return <DemoOverview />;
  }

  const m = metrics;
  const maxQueries = m
    ? Math.max(1, ...m.weekly_queries.map((w) => w.queries))
    : 0;

  return (
    <div className="mx-auto w-full max-w-5xl">
      <PageHeader
        title="使用看板"
        description="知识库的使用与健康度总览。北极星指标是「答案采纳率」——用户点开引用、追问或点赞的比例。"
      />

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-seal/30 bg-seal-wash px-4 py-3 text-[13px] leading-5 text-seal-deep"
        >
          {error}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="今日问答" value={m?.today_queries ?? "—"} />
        <MetricCard
          label="答案采纳率"
          value={m?.acceptance_rate ?? "—"}
          unit={m?.acceptance_rate != null ? "%" : undefined}
          hint="待采纳行为埋点（点赞/引用点击）"
        />
        <MetricCard
          label="无答案率"
          value={m?.no_answer_rate ?? "—"}
          unit={m?.no_answer_rate != null ? "%" : undefined}
          hint="健康区间 5–20%"
          good={m?.no_answer_rate != null ? m.no_answer_rate <= 20 : undefined}
        />
        <MetricCard
          label="引用率"
          value={m?.citation_rate ?? "—"}
          unit={m?.citation_rate != null ? "%" : undefined}
          hint="含有效引用的回答占比"
          good={m?.citation_rate != null ? m.citation_rate >= 95 : undefined}
        />
        <MetricCard
          label="解析失败率"
          value={m?.parse_fail_rate ?? "—"}
          unit={m?.parse_fail_rate != null ? "%" : undefined}
          hint="目标 ≤ 5%"
          good={m?.parse_fail_rate != null ? m.parse_fail_rate <= 5 : undefined}
        />
        <MetricCard label="首答时延 p95" value={m?.latency_p95 ?? "—"} hint="待计时埋点" />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        {/* 近 7 日问答量 */}
        <section className="rounded-xl border border-line bg-paper p-5 lg:col-span-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-ink">近 7 日问答量</h2>
            <span className="text-[11px] text-ink-faint">来自审计埋点</span>
          </div>
          <div className="mt-5 flex h-44 items-end gap-3">
            {(m?.weekly_queries ?? []).map((w) => {
              // 用像素高度：flex 列内百分比高度无法解析
              const h = Math.max(6, Math.round((w.queries / maxQueries) * 150));
              const label = WEEKDAYS[new Date(w.day + "T00:00:00").getDay()];
              return (
                <div key={w.day} className="flex flex-1 flex-col items-center gap-2">
                  <span className="font-mono text-[10px] text-ink-faint">{w.queries}</span>
                  <div
                    className="w-full max-w-9 rounded-t bg-indigo/85"
                    style={{ height: `${h}px` }}
                    title={`${w.day}：${w.queries} 次`}
                  />
                  <span className="text-[11px] text-ink-soft">{label}</span>
                </div>
              );
            })}
            {m && m.weekly_queries.length === 0 && (
              <p className="w-full py-10 text-center text-xs text-ink-faint">
                最近 7 天还没有问答记录。
              </p>
            )}
          </div>
        </section>

        {/* 最近问题 */}
        <section className="rounded-xl border border-line bg-paper p-5 lg:col-span-2">
          <h2 className="text-sm font-medium text-ink">最近问题</h2>
          <ul className="mt-3 divide-y divide-line">
            {(m?.recent_questions ?? []).map((q, i) => (
              <li key={i} className="flex items-center gap-2 py-2.5">
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    q.no_answer ? "bg-seal" : "bg-jade",
                  )}
                />
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                  {q.query}
                </span>
                <span className="font-mono text-[11px] text-ink-faint">{q.at}</span>
              </li>
            ))}
            {m && m.recent_questions.length === 0 && (
              <li className="py-6 text-center text-xs text-ink-faint">
                还没有问答记录。
              </li>
            )}
          </ul>
          <p className="mt-3 text-[11px] leading-4 text-ink-faint">
            红点为触发无答案兜底的问题——它们提示知识库缺什么内容。
          </p>
        </section>
      </div>

      {m && (
        <p className="mt-4 rounded-lg border border-dashed border-line-strong bg-paper px-4 py-3 text-xs leading-5 text-ink-soft">
          文档库：共 {m.documents.total} 份（已完成 {m.documents.completed} · 解析中{" "}
          {m.documents.processing} · 失败 {m.documents.failed}）· 助手回答{" "}
          {m.conversations.assistant_messages} 条。采纳率与时延分位需前端行为埋点与计时埋点后开放。
        </p>
      )}
    </div>
  );
}

function DemoOverview() {
  const m = demoMetrics;
  const maxQueries = Math.max(...m.weekly.map((w) => w.queries));
  return (
    <div className="mx-auto h-full w-full max-w-5xl overflow-y-auto">
      <PageHeader
        title="使用看板"
        description="知识库的使用与健康度总览。北极星指标是「答案采纳率」——用户点开引用、追问或点赞的比例。"
        actions={<PreviewTag label="演示数据" />}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <MetricCard label="今日问答" value={m.todayQueries} />
        <MetricCard label="答案采纳率" value={m.acceptanceRate} unit="%" hint="目标 ≥ 60%" good={m.acceptanceRate >= 60} />
        <MetricCard label="无答案率" value={m.noAnswerRate} unit="%" hint="健康区间 5–20%" good={m.noAnswerRate <= 20} />
        <MetricCard label="引用率" value={m.citationRate} unit="%" hint="含有效引用的回答占比" good={m.citationRate >= 95} />
        <MetricCard label="解析失败率" value={m.parseFailRate} unit="%" hint="目标 ≤ 5%" good={m.parseFailRate <= 5} />
        <MetricCard label="首答时延 p95" value={m.latencyP95} hint="目标 ≤ 5s" good />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-5">
        <section className="rounded-xl border border-line bg-paper p-5 lg:col-span-3">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-medium text-ink">近 7 日问答量</h2>
            <span className="text-[11px] text-ink-faint">灰色为无答案占比</span>
          </div>
          <div className="mt-5 flex h-44 items-end gap-3">
            {m.weekly.map((w) => {
              const h = Math.max(6, Math.round((w.queries / maxQueries) * 150));
              const noAnswerH = Math.round((w.noAnswer / w.queries) * h);
              return (
                <div key={w.day} className="flex flex-1 flex-col items-center gap-2">
                  <span className="font-mono text-[10px] text-ink-faint">{w.queries}</span>
                  <div
                    className="relative w-full max-w-9 overflow-hidden rounded-t bg-indigo/85"
                    style={{ height: `${h}px` }}
                    title={`${w.day}：${w.queries} 次，其中无答案 ${w.noAnswer} 次`}
                  >
                    <span
                      className="absolute inset-x-0 top-0 bg-ink-faint/50"
                      style={{ height: `${noAnswerH}px` }}
                    />
                  </div>
                  <span className="text-[11px] text-ink-soft">{w.day}</span>
                </div>
              );
            })}
          </div>
        </section>

        <section className="rounded-xl border border-line bg-paper p-5 lg:col-span-2">
          <h2 className="text-sm font-medium text-ink">最近问题</h2>
          <ul className="mt-3 divide-y divide-line">
            {m.recentQuestions.map((q) => (
              <li key={q.q} className="flex items-center gap-2 py-2.5">
                <span
                  aria-hidden="true"
                  className={cn(
                    "size-1.5 shrink-0 rounded-full",
                    q.ok ? "bg-jade" : "bg-seal",
                  )}
                />
                <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                  {q.q}
                </span>
                <span className="font-mono text-[11px] text-ink-faint">{q.at}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[11px] leading-4 text-ink-faint">
            红点为触发无答案兜底的问题——它们提示知识库缺什么内容。
          </p>
        </section>
      </div>

      <p className="mt-4 rounded-lg border border-dashed border-line-strong bg-paper px-4 py-3 text-xs leading-5 text-ink-soft">
        本页为产品规划（M5 使用看板）的前端预览：指标口径与布局已定稿，
        开启后端后自动切换为真实数据。
      </p>
    </div>
  );
}
