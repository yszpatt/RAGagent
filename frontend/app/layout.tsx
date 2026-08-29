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
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f2f4f6" },
    { media: "(prefers-color-scheme: dark)", color: "#141920" },
  ],
};

// 首帧防白闪：渲染前读 localStorage(kp.theme.v1) 把 .dark 挂到 <html>。
// 逻辑与 components/theme-toggle.tsx 的 applyTheme 保持一致。
const themeInitScript = `(function(){try{var t=localStorage.getItem("kp.theme.v1");function add(){document.documentElement.classList.add("dark");}if(t==="dark"){add();return;}if(t==="light"){return;}if(window.matchMedia("(prefers-color-scheme: dark)").matches){add();}}catch(e){}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="h-full antialiased" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body className="min-h-full">
        <DemoProvider>
          <AppShell>{children}</AppShell>
        </DemoProvider>
      </body>
    </html>
  );
}
