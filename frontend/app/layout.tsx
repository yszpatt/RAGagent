import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KnowledgePilot",
  description: "企业知识库 RAG 问答",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <nav className="border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div className="max-w-3xl mx-auto flex items-center gap-6 px-8 py-3">
            <a href="/" className="font-bold text-gray-900 dark:text-gray-100">
              KnowledgePilot
            </a>
            <a
              href="/"
              className="text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            >
              问答
            </a>
            <a
              href="/upload"
              className="text-sm text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100"
            >
              上传文档
            </a>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
