import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";
import { DemoProvider } from "@/lib/demo-context";

export const metadata: Metadata = {
  title: "KnowledgePilot · 企业知识库问答",
  description:
    "上传文档、自然语言提问，返回带引用溯源的答案；低置信自动兜底，不编造。",
};

export const viewport = {
  themeColor: "#f2f4f6",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full">
        <DemoProvider>
          <AppShell>{children}</AppShell>
        </DemoProvider>
      </body>
    </html>
  );
}
