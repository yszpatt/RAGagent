"use client";

// 主题切换：亮色 → 暗色 → 跟随系统 三态循环。
// 状态持久化在 localStorage(kp.theme.v1)；首次进入的防闪烁由
// layout.tsx <head> 内联脚本负责（渲染前把 .dark 类挂到 <html>）。
// 换肤机制：globals.css 在 .dark 下覆盖 --color-* 变量，组件零改动。
// 设置页的主题分段选择器（ThemeSegmented）与这里共用同一存储，
// 通过 kp-theme-changed 事件互相同步 UI。

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { usePrefs } from "@/lib/prefs";

export type ThemeMode = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "kp.theme.v1";
const THEME_EVENT = "kp-theme-changed";

export function applyTheme(mode: ThemeMode) {
  const dark =
    mode === "dark" ||
    (mode === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function readThemeMode(): ThemeMode {
  const saved = localStorage.getItem(THEME_STORAGE_KEY);
  return saved === "light" || saved === "dark" || saved === "system"
    ? saved
    : "system";
}

export function writeThemeMode(mode: ThemeMode) {
  localStorage.setItem(THEME_STORAGE_KEY, mode);
  applyTheme(mode);
  window.dispatchEvent(new Event(THEME_EVENT));
}

/** 监听主题被其他入口（设置页）修改；返回清理函数。 */
export function useThemeSync(onChange: (mode: ThemeMode) => void) {
  useEffect(() => {
    const handler = () => onChange(readThemeMode());
    window.addEventListener(THEME_EVENT, handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener(THEME_EVENT, handler);
      window.removeEventListener("storage", handler);
    };
  }, [onChange]);
}

export function ThemeToggle({ iconOnly = false }: { iconOnly?: boolean }) {
  const { t } = usePrefs();
  const [mode, setMode] = useState<ThemeMode>("system");

  useEffect(() => {
    const initial = readThemeMode();
    setMode(initial);
    applyTheme(initial);
    // 跟随系统时监听系统主题变化
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (readThemeMode() === "system") applyTheme("system");
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useThemeSync((m) => setMode(m));

  const cycle = () => {
    const next: ThemeMode =
      mode === "light" ? "dark" : mode === "dark" ? "system" : "light";
    setMode(next);
    writeThemeMode(next);
  };

  const Icon = mode === "light" ? Sun : mode === "dark" ? Moon : Monitor;
  const label =
    mode === "light"
      ? t("theme.light")
      : mode === "dark"
        ? t("theme.dark")
        : t("theme.system");

  return (
    <button
      onClick={cycle}
      aria-label={t("theme.aria").replace("{label}", label)}
      title={`${t("theme.aria").replace("{label}", label)}`}
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

/** 设置页用：三选一分段控件（与侧栏按钮同存储、事件互相同步） */
export function ThemeSegmented() {
  const { t } = usePrefs();
  const [mode, setMode] = useState<ThemeMode>("system");

  useEffect(() => setMode(readThemeMode()), []);
  useThemeSync((m) => setMode(m));

  const options: { key: ThemeMode; label: string; icon: typeof Sun }[] = [
    { key: "light", label: t("theme.light"), icon: Sun },
    { key: "dark", label: t("theme.dark"), icon: Moon },
    { key: "system", label: t("theme.system"), icon: Monitor },
  ];

  return (
    <div className="inline-flex rounded-lg border border-line bg-porcelain p-0.5">
      {options.map(({ key, label, icon: Icon }) => (
        <button
          key={key}
          onClick={() => {
            setMode(key);
            writeThemeMode(key);
          }}
          aria-pressed={mode === key}
          className={
            "flex items-center gap-1.5 rounded-[6px] px-3 py-1.5 text-xs transition-colors " +
            (mode === key
              ? "bg-paper font-medium text-indigo-deep shadow-sm"
              : "text-ink-soft hover:text-ink")
          }
        >
          <Icon size={13} />
          {label}
        </button>
      ))}
    </div>
  );
}
