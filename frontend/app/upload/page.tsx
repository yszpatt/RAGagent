"use client";
import { useState } from "react";

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function pollStatus(docId: string) {
    for (let i = 0; i < 15; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const res = await fetch(`/api/v1/documents/${docId}`);
        if (res.ok) {
          const data = await res.json();
          setStatus(data.data?.status ?? "");
          if (data.data?.status === "completed" || data.data?.status === "failed") return;
        }
      } catch {
        // 忽略轮询错误，继续
      }
    }
  }

  async function upload() {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult("");
    setStatus("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/v1/documents/upload", { method: "POST", body: fd });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`上传失败 (${res.status}): ${text.slice(0, 200)}`);
      }
      const data = await res.json();
      setResult(`document_id: ${data.document_id} · status: ${data.status}`);
      void pollStatus(data.document_id as string);
    } catch (e) {
      setError(e instanceof Error ? e.message : "上传出错");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex-1 w-full max-w-3xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">上传文档</h1>
      <input
        type="file"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block mb-3 text-gray-900 dark:text-gray-100"
      />
      <button
        onClick={upload}
        disabled={loading || !file}
        className="px-5 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50 hover:bg-blue-700"
      >
        {loading ? "上传中…" : "上传"}
      </button>
      {error && (
        <p className="mt-4 p-4 bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300 rounded-lg">
          {error}
        </p>
      )}
      {result && (
        <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg text-gray-900 dark:text-gray-100">
          {result}
          {status && (
            <p className="mt-2 text-sm">
              接入状态：{status}
              {status === "pending" || status === "processing" ? " …" : ""}
            </p>
          )}
        </div>
      )}
      <p className="mt-6 text-sm text-gray-500 dark:text-gray-400">
        <a href="/" className="underline">
          ← 返回问答
        </a>
      </p>
    </main>
  );
}
