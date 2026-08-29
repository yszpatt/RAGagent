"use client";

// 问答主页：左侧会话列表 + 卷宗条目式问答流 + 来源案卷抽屉。
// 真实模式：调用后端 /api/v1/chat（同步返回，前端做打字机呈现）；
// 演示模式：全部数据来自 lib/demo-data.ts。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { LibraryBig, Plus, SendHorizontal } from "lucide-react";
import { TurnItem, sourceFromCitation } from "@/components/chat/turn-item";
import { SourceDrawer } from "@/components/chat/source-drawer";
import { EmptyState } from "@/components/ui/page";
import { Badge, PreviewTag } from "@/components/ui/badge";
import { useDemoMode } from "@/lib/demo-context";
import { demoAsk, demoConversations } from "@/lib/demo-data";
import {
  ask as askBackend,
  fetchMessages,
  listConversations,
} from "@/lib/api";
import type { Citation, Conversation, SourceRef, Turn } from "@/lib/types";
import { cn, newId } from "@/lib/utils";

const SAMPLE_QUESTIONS = [
  "供应商合同里违约金条款是怎么约定的？",
  "出差住宿费报销标准是多少？",
  "年假最多可以顺延到什么时候？",
];

/** 后端消息序列（user/assistant 交替）→ 前端问答回合 */
function messagesToTurns(
  msgs: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    citations: Citation[] | null;
    no_answer: boolean;
    created_at: string;
  }>,
): Turn[] {
  const turns: Turn[] = [];
  let current: Turn | null = null;
  for (const m of msgs) {
    if (m.role === "user") {
      current = {
        id: m.id,
        query: m.content,
        answer: "",
        no_answer: false,
        citations: [],
        at: Date.parse(m.created_at) || Date.now(),
      };
      turns.push(current);
    } else {
      if (!current) continue; // 缺少配对 user 消息的脏数据，跳过
      current.answer = m.content;
      current.no_answer = m.no_answer;
      current.citations = m.citations ?? [];
      current.at = Date.parse(m.created_at) || current.at;
    }
  }
  return turns;
}

export default function ChatPage() {
  const { demo, backend } = useDemoMode();

  const [realConvs, setRealConvs] = useState<Conversation[]>([]);
  const [demoConvos, setDemoConvos] = useState<Conversation[]>(demoConversations);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draftTurns, setDraftTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [typingTurnId, setTypingTurnId] = useState<string | null>(null);
  const [revealedCount, setRevealedCount] = useState(0);
  const [source, setSource] = useState<SourceRef | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);

  // 真实模式：会话列表来自后端；演示模式：内存 fixtures
  useEffect(() => {
    if (demo) return;
    listConversations()
      .then((list) =>
        setRealConvs(
          list.map((c) => ({
            id: c.id,
            title: c.title || "（无标题会话）",
            turns: [], // 历史按需加载
            updatedAt: Date.parse(c.last_message_at ?? c.created_at) || 0,
          })),
        ),
      )
      .catch(() => {
        /* 后端瞬断：保留当前列表 */
      });
  }, [demo]);

  // 切换模式时回到新会话，避免两套数据混排
  useEffect(() => {
    setActiveId(null);
    setDraftTurns([]);
    setError("");
  }, [demo]);

  const convs = demo ? demoConvos : realConvs;
  const activeConv = useMemo(
    () => convs.find((c) => c.id === activeId) ?? null,
    [convs, activeId],
  );
  const turns = activeConv ? activeConv.turns : draftTurns;

  // 选中未加载历史的会话 → 拉取消息
  useEffect(() => {
    if (demo || !activeConv || activeConv.turns.length > 0) return;
    let cancelled = false;
    fetchMessages(activeConv.id)
      .then((msgs) => {
        if (cancelled) return;
        const loaded = messagesToTurns(msgs);
        setRealConvs((prev) =>
          prev.map((c) => (c.id === activeConv.id ? { ...c, turns: loaded } : c)),
        );
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载会话失败");
      });
    return () => {
      cancelled = true;
    };
  }, [demo, activeConv]);

  // 打字机：新答案到达后按帧推进
  useEffect(() => {
    if (!typingTurnId) return;
    const all = [...convs.map((c) => c.turns).flat(), ...draftTurns];
    const t = all.find((x) => x.id === typingTurnId);
    if (!t) {
      setTypingTurnId(null);
      return;
    }
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setTypingTurnId(null);
      return;
    }
    let count = 0;
    let raf = 0;
    let last = 0;
    const step = (ts: number) => {
      if (ts - last > 20) {
        count = Math.min(t.answer.length, count + 5);
        setRevealedCount(count);
        last = ts;
      }
      if (count < t.answer.length) {
        raf = requestAnimationFrame(step);
      } else {
        setTypingTurnId(null);
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [typingTurnId, convs, draftTurns]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, loading]);

  const commitTurn = useCallback(
    (turn: Turn, convId: string | null) => {
      if (demo) {
        // 演示问答追加进内存中的演示会话（不持久化）
        setDemoConvos((prev) => {
          const target = convId && prev.find((c) => c.id === convId);
          if (target) {
            return prev.map((c) =>
              c.id === convId
                ? { ...c, turns: [...c.turns, turn], updatedAt: turn.at }
                : c,
            );
          }
          const created: Conversation = {
            id: convId ?? newId("demo"),
            title: turn.query.slice(0, 18),
            turns: [turn],
            updatedAt: turn.at,
          };
          setActiveId(created.id);
          return [created, ...prev];
        });
        setDraftTurns([]);
        return;
      }
      // 真实模式：后端已持久化，本地只做展示同步
      setRealConvs((prev) => {
        const target = convId && prev.find((c) => c.id === convId);
        if (target) {
          return prev.map((c) =>
            c.id === convId
              ? { ...c, turns: [...c.turns, turn], updatedAt: turn.at }
              : c,
          );
        }
        const created: Conversation = {
          id: convId ?? newId("c"),
          title: turn.query.slice(0, 18),
          turns: [turn],
          updatedAt: turn.at,
        };
        setActiveId(created.id);
        return [created, ...prev];
      });
      setDraftTurns([]);
    },
    [demo],
  );

  async function handleAsk() {
    const query = input.trim();
    if (!query || loading) return;
    setInput("");
    setError("");
    setLoading(true);

    // 先展示用户的问题
    const placeholderId = newId("t");
    setDraftTurns([
      {
        id: placeholderId,
        query,
        answer: "",
        no_answer: false,
        citations: [],
        at: Date.now(),
      },
    ]);

    try {
      const res = demo
        ? await withDelay(demoAsk(query), 900)
        : await askBackend(query, demo ? undefined : activeId ?? undefined);
      const turn: Turn = {
        id: placeholderId,
        query,
        answer: res.answer,
        no_answer: res.no_answer,
        citations: res.citations ?? [],
        at: Date.now(),
      };
      commitTurn(turn, res.conversation_id ?? (demo ? null : activeId));
      if (!res.no_answer) {
        setRevealedCount(0);
        setTypingTurnId(turn.id);
      }
    } catch (e) {
      setDraftTurns([]);
      setError(
        (e instanceof Error ? e.message : "请求出错") +
          "。请确认后端已启动（uvicorn app.main:app），或在左下角开启演示模式。",
      );
    } finally {
      setLoading(false);
    }
  }

  function openSource(citation: Citation, index: number) {
    setSource(sourceFromCitation(citation, index, demo));
  }

  return (
    <div className="mx-auto flex h-full w-full max-w-6xl gap-6 overflow-hidden">
      {/* 会话列表（桌面端）：独立滚动，不挤占问答列 */}
      <aside className="hidden h-full w-56 shrink-0 flex-col md:flex">
        <div className="mb-3 flex shrink-0 items-center justify-between px-1">
          <h2 className="text-xs font-medium tracking-widest text-ink-faint">
            会话
          </h2>
          <button
            onClick={() => {
              setActiveId(null);
              setDraftTurns([]);
            }}
            className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-indigo hover:bg-indigo-wash"
          >
            <Plus size={13} />
            新会话
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          {convs.length === 0 && (
            <p className="px-1 py-2 text-xs leading-5 text-ink-faint">
              提问后会自动保存在本机，此列表不会上传。
            </p>
          )}
          {convs.map((c) => (
            <button
              key={c.id}
              onClick={() => {
                setActiveId(c.id);
                setDraftTurns([]);
              }}
              aria-current={activeId === c.id ? "true" : undefined}
              className={cn(
                "break-words rounded-md px-2.5 py-2 text-left text-[13px] leading-snug transition-colors",
                activeId === c.id
                  ? "bg-indigo-wash font-medium text-indigo-deep"
                  : "text-ink-soft hover:bg-porcelain hover:text-ink",
              )}
            >
              {c.title}
              <span className="ml-1.5 font-mono text-[10px] text-ink-faint">
                {c.turns.length}轮
              </span>
            </button>
          ))}
          {demo && (
            <p className="mt-2 px-1 text-[11px] leading-4 text-ink-faint">
              演示会话不占用本机存储。
            </p>
          )}
        </div>
      </aside>

      {/* 问答主列：自身成列，中间问答区滚动，输入区固定在底部 */}
      <section className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
        <header className="mb-4 flex flex-wrap items-center gap-2">
          <h1 className="min-w-0 font-display text-lg font-bold tracking-wide text-ink break-words">
            {activeConv ? activeConv.title : "新会话"}
          </h1>
          {demo && <PreviewTag label="演示模式" />}
          {turns.length > 0 && (
            <span className="font-mono text-[11px] text-ink-faint">
              {turns.length} 轮问答
            </span>
          )}
          <button
            onClick={() => {
              setActiveId(null);
              setDraftTurns([]);
            }}
            className="ml-auto flex items-center gap-1 rounded-md border border-line bg-paper px-2 py-1 text-xs text-ink-soft hover:border-line-strong hover:text-ink md:hidden"
          >
            <Plus size={13} />
            新会话
          </button>
        </header>

        {/* 移动端会话切换：横向滚动，独立成条，不挤占问答区 */}
        {convs.length > 0 && (
          <div className="mb-3 flex max-h-12 shrink-0 gap-1.5 overflow-x-auto pb-1 md:hidden">
            <button
              onClick={() => {
                setActiveId(null);
                setDraftTurns([]);
              }}
              className={cn(
                "shrink-0 rounded-full border px-3 py-1 text-xs",
                activeId === null
                  ? "border-indigo bg-indigo-wash text-indigo-deep"
                  : "border-line text-ink-soft",
              )}
            >
              新会话
            </button>
            {convs.map((c) => (
              <button
                key={c.id}
                onClick={() => setActiveId(c.id)}
                className={cn(
                  "shrink-0 rounded-full border px-3 py-1 text-xs",
                  activeId === c.id
                    ? "border-indigo bg-indigo-wash text-indigo-deep"
                    : "border-line text-ink-soft",
                )}
              >
                {c.title}
              </button>
            ))}
          </div>
        )}

        {turns.length === 0 && !loading ? (
          <div className="flex flex-1 items-center justify-center">
            <div className="w-full max-w-lg text-center">
              <span
                aria-hidden="true"
                className="mx-auto flex size-14 items-center justify-center rounded-[6px] bg-seal font-display text-3xl font-bold text-paper"
              >
                知
              </span>
              <h2 className="mt-4 font-display text-xl font-semibold text-balance text-ink">
                问一个业务问题，答案必带出处
              </h2>
              <p className="mx-auto mt-2 max-w-sm text-[13px] leading-5 text-ink-soft">
                系统在已上传的知识库中检索并生成答案，每条结论都标注来源页码；
                检索不到的内容会明确告知，不编造。
              </p>
              <div className="mt-6 flex flex-col items-center gap-2">
                {SAMPLE_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                    }}
                    className="w-full rounded-lg border border-line bg-paper px-4 py-2.5 text-left text-[13px] text-ink-soft transition-colors hover:border-indigo/40 hover:text-ink"
                  >
                    {q}
                  </button>
                ))}
              </div>
              {backend === "down" && (
                <p className="mt-6 text-xs text-ink-faint">
                  后端未连接，当前为演示数据。去{" "}
                  <Link href="/documents" className="text-indigo underline underline-offset-2">
                    知识库
                  </Link>{" "}
                  上传文档后即可真实问答。
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
            {turns.map((t, i) => {
              const typing = typingTurnId === t.id;
              return (
                <TurnItem
                  key={t.id}
                  turn={t}
                  index={i}
                  demo={demo}
                  typing={typing}
                  displayAnswer={typing ? t.answer.slice(0, revealedCount) : undefined}
                  onCitation={openSource}
                />
              );
            })}

            {loading && (
              <div
                aria-live="polite"
                className="rise flex items-center gap-2 rounded-xl border border-dashed border-line-strong bg-paper/60 px-5 py-4 text-[13px] text-ink-soft"
              >
                <span className="flex gap-1" aria-hidden="true">
                  <i className="size-1.5 animate-bounce rounded-full bg-indigo [animation-delay:0ms] motion-reduce:animate-none" />
                  <i className="size-1.5 animate-bounce rounded-full bg-indigo [animation-delay:150ms] motion-reduce:animate-none" />
                  <i className="size-1.5 animate-bounce rounded-full bg-indigo [animation-delay:300ms] motion-reduce:animate-none" />
                </span>
                检索知识库并生成答案…
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="mt-3 rounded-lg border border-seal/30 bg-seal-wash px-4 py-3 text-[13px] leading-5 text-seal-deep"
          >
            {error}
          </p>
        )}

        {/* 输入区 */}
        <div className="mt-4 rounded-xl border border-line bg-paper p-3 shadow-sm focus-within:border-indigo/50">
          <label htmlFor="chat-input" className="sr-only">
            输入问题
          </label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              // Enter 发送；Shift+Enter 换行；isComposing 守卫中文输入法
              // 选词回车（fcitx5 确认候选词也触发 Enter），避免误发送
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                void handleAsk();
              }
            }}
            rows={2}
            placeholder="例如：供应商合同里违约金是怎么约定的？"
            className="w-full resize-none bg-transparent px-1 text-[14px] leading-6 text-ink placeholder:text-ink-faint focus:outline-none"
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <span className="hidden text-[11px] text-ink-faint sm:inline">
              Enter 发送 · Shift+Enter 换行 · 答案均标注来源页码
            </span>
            <div className="flex shrink-0 items-center gap-2">
              <Link
                href="/documents"
                className="flex items-center gap-1 whitespace-nowrap rounded-md px-2 py-1.5 text-xs text-ink-soft hover:bg-porcelain hover:text-ink"
              >
                <LibraryBig size={14} />
                知识库
              </Link>
              <button
                onClick={() => void handleAsk()}
                disabled={loading || !input.trim()}
                className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg bg-indigo px-4 py-2 text-[13px] font-medium text-paper transition-colors hover:bg-indigo-deep disabled:cursor-not-allowed disabled:opacity-45"
              >
                <SendHorizontal size={14} />
                提问
              </button>
            </div>
          </div>
        </div>
      </section>

      <SourceDrawer source={source} onClose={() => setSource(null)} demo={demo} />
    </div>
  );
}

function withDelay<T>(value: T, ms: number): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms));
}
