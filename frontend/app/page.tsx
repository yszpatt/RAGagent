"use client";
import { useState } from "react";

interface Citation {
  chunk_id: string;
  page: number | null;
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [noAnswer, setNoAnswer] = useState(false);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function ask() {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`请求失败 (${res.status}): ${text.slice(0, 200)}`);
      }
      const data = await res.json();
      setAnswer(data.answer ?? "");
      setNoAnswer(data.no_answer ?? false);
      setCitations(data.citations ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "请求出错");
      setAnswer("");
      setNoAnswer(false);
      setCitations([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">知识问答</h1>
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
        }}
        placeholder="问一个关于公司知识库的问题…"
        className="w-full p-3 border border-gray-300 rounded-lg bg-white text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100 min-h-[100px]"
      />
      <div className="flex items-center gap-3">
        <button
          onClick={ask}
          disabled={loading}
          className="mt-3 px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50 hover:bg-blue-700"
        >
          {loading ? "思考中…" : "提问"}
        </button>
        <span className="mt-3 text-xs text-gray-400">Ctrl/⌘ + Enter 快捷提问</span>
      </div>
      {error && (
        <p className="mt-4 p-4 bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300 rounded-lg">
          {error}
        </p>
      )}
      {noAnswer && (
        <p className="mt-4 p-4 bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300 rounded-lg">
          未找到相关信息，请尝试换个问法。
        </p>
      )}
      {answer && !noAnswer && (
        <div className="mt-4 p-4 bg-gray-50 border border-gray-200 rounded-lg text-gray-900 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100 whitespace-pre-wrap">
          {answer}
        </div>
      )}
      {citations.length > 0 && (
        <div className="mt-3 text-sm text-blue-700 dark:text-blue-400">
          {citations.map((c, i) => (
            <div key={i}>来源：第 {c.page ?? "?"} 页</div>
          ))}
        </div>
      )}
    </main>
  );
}
