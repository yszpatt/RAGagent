"use client";

// 应用壳：桌面端左侧「档案室」导航 + 移动端顶栏。
// 底部提供后端连接状态与演示模式开关。

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LibraryBig,
  MessageSquareText,
  ScrollText,
  ShieldCheck,
  Gauge,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDemoMode } from "@/lib/demo-context";

const NAV_MAIN = [
  { href: "/", label: "问答", icon: MessageSquareText },
  { href: "/documents", label: "知识库", icon: LibraryBig },
];

const NAV_ADMIN = [
  { href: "/admin/overview", label: "看板", icon: Gauge },
  { href: "/admin/permissions", label: "权限", icon: ShieldCheck },
  { href: "/admin/audit", label: "审计", icon: ScrollText },
];

function BrandMark({ size = "size-8" }: { size?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "flex items-center justify-center rounded-[4px] bg-seal font-display font-bold text-paper select-none",
        size,
      )}
      style={{ fontSize: size === "size-8" ? 17 : 14 }}
    >
      知
    </span>
  );
}

function NavLink({
  href,
  label,
  icon: Icon,
  active,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
        active
          ? "bg-indigo-wash font-medium text-indigo-deep"
          : "text-ink-soft hover:bg-porcelain hover:text-ink",
      )}
    >
      <Icon size={16} />
      {label}
    </Link>
  );
}

function DemoSwitch() {
  const { demo, backend, toggleDemo, refreshBackend } = useDemoMode();
  const probing = backend === "probing";
  return (
    <div className="rounded-lg border border-line bg-porcelain px-3 py-2.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-ink">演示模式</span>
        <button
          role="switch"
          aria-checked={demo}
          aria-label="切换演示模式"
          disabled={probing}
          onClick={() => toggleDemo(!demo)}
          className={cn(
            "relative h-5 w-9 rounded-full border transition-colors disabled:opacity-50",
            demo ? "border-seal bg-seal" : "border-line-strong bg-paper",
          )}
        >
          <span
            className={cn(
              "absolute top-0.5 size-3.5 rounded-full bg-paper shadow transition-all",
              demo ? "left-[18px]" : "left-0.5 bg-ink-faint",
            )}
          />
        </button>
      </div>
      <p className="mt-1.5 flex items-center gap-1.5 text-[11px] leading-4 text-ink-soft">
        <span
          aria-hidden="true"
          className={cn(
            "size-1.5 rounded-full",
            probing ? "bg-ink-faint" : backend === "up" ? "bg-jade" : "bg-seal",
          )}
        />
        {probing
          ? "正在探测后端…"
          : backend === "up"
            ? "后端已连接"
            : "后端未连接，展示演示数据"}
        {!probing && (
          <button
            onClick={refreshBackend}
            className="ml-auto text-indigo hover:text-indigo-deep"
          >
            重试
          </button>
        )}
      </p>
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { backend } = useDemoMode();

  return (
    <div className="flex min-h-screen">
      {/* 跳转到主内容（键盘用户） */}
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:border focus:border-line focus:bg-paper focus:px-3 focus:py-2 focus:text-sm focus:text-ink"
      >
        跳到主内容
      </a>
      {/* 桌面侧栏 */}
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-paper px-3 py-4 lg:flex">
        <Link href="/" className="mb-6 flex items-center gap-2.5 px-2">
          <BrandMark />
          <span className="font-display text-lg font-bold tracking-wide text-ink">
            KnowledgePilot
          </span>
        </Link>

        <nav aria-label="主导航" className="flex flex-col gap-0.5">
          {NAV_MAIN.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={pathname === item.href}
            />
          ))}
        </nav>

        <div className="mt-6 mb-1 flex items-center gap-2 px-3">
          <span className="text-[11px] font-medium tracking-widest text-ink-faint">
            管理
          </span>
          <span className="rounded-sm border border-seal/40 px-1 font-mono text-[10px] leading-4 text-seal">
            预览
          </span>
        </div>
        <nav aria-label="管理导航" className="flex flex-col gap-0.5">
          {NAV_ADMIN.map((item) => (
            <NavLink
              key={item.href}
              {...item}
              active={pathname === item.href}
            />
          ))}
        </nav>

        <div className="mt-auto pt-4">
          <DemoSwitch />
        </div>
      </aside>

      {/* 移动端顶栏 */}
      <div
        className="fixed inset-x-0 top-0 z-40 border-b border-line bg-paper lg:hidden"
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <div className="flex items-center gap-2 px-4 py-2.5">
          <BrandMark size="size-7" />
          <span className="font-display text-base font-bold text-ink">
            KnowledgePilot
          </span>
          <span
            aria-hidden="true"
            className={cn("ml-auto size-2 rounded-full", backendDot(backend))}
          />
        </div>
        <nav
          aria-label="移动端导航"
          className="flex gap-1 overflow-x-auto px-3 pb-2"
        >
          {[...NAV_MAIN, ...NAV_ADMIN].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
              className={cn(
                "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs",
                pathname === item.href
                  ? "bg-indigo-wash font-medium text-indigo-deep"
                  : "text-ink-soft",
              )}
            >
              <item.icon size={14} />
              {item.label}
            </Link>
          ))}
        </nav>
      </div>

      <main
        id="main"
        className="min-w-0 flex-1 px-4 pb-16 pt-20 sm:px-6 lg:px-10 lg:pt-8"
      >
        {children}
      </main>
    </div>
  );
}

function backendDot(state: string): string {
  if (state === "up") return "bg-jade";
  if (state === "down") return "bg-seal";
  return "bg-ink-faint";
}
