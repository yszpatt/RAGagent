"use client";

// 主题切换：亮色 → 暗色 → 跟随系统 三态循环。
// 状态持久化在 localStorage(kp.theme.v1)；首次进入的防闪烁由
// layout.tsx <head> 内联脚本负责（渲染前把 .dark 类挂到 <html>）。
// 换肤机制：globals.css 在 .dark 下覆盖 --color-* 变量，组件零改动。

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";

type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "kp.theme.v1";

function applyTheme(mode: ThemeMode) {
  const dark =
    mode === "dark" ||
    (mode === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function ThemeToggle({ iconOnly = false }: { iconOnly?: boolean }) {
  const [mode, setMode] = useState<ThemeMode>("system");

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    const initial: ThemeMode =
      saved === "light" || saved === "dark" || saved === "system"
        ? saved
        : "system";
    setMode(initial);
    applyTheme(initial);
    // 跟随系统时监听系统主题变化
    if (initial === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = () => applyTheme("system");
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
  }, []);

  const cycle = () => {
    const next: ThemeMode =
      mode === "light" ? "dark" : mode === "dark" ? "system" : "light";
    setMode(next);
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  };

  const Icon = mode === "light" ? Sun : mode === "dark" ? Moon : Monitor;
  const label = mode === "light" ? "亮色" : mode === "dark" ? "暗色" : "跟随系统";

  return (
    <button
      onClick={cycle}
      aria-label={`主题：${label}，点击切换`}
      title={`主题：${label}（点击切换）`}
      className={
        iconOnly
          ? "rounded-md p-1.5 text-ink-soft transition-colors hover:bg-porcelain hover:text-ink"
          : "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-xs text-ink-soft transition-colors hover:bg-porcelain hover:text-ink"
      }
    >
      <Icon size={14} />
      {!iconOnly && <span>{label}</span>}
    </button>
  );
}
