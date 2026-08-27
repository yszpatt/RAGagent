"use client";
import { useState } from "react";

export default function Upload() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function upload() {
    if (!file) return;
    setLoading(true);
    setError("");
    setResult("");
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
        <p className="mt-4 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg text-gray-900 dark:text-gray-100">
          {result}
        </p>
      )}
      <p className="mt-6 text-sm text-gray-500 dark:text-gray-400">
        <a href="/" className="underline">
          ← 返回问答
        </a>
      </p>
    </main>
  );
}
