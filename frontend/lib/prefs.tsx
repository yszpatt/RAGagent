"use client";

// 前端偏好上下文（本机演示，不上传）：界面语言、动效开关、当前演示身份。
// 主题不在这里管理 —— 沿用 components/theme-toggle.tsx 的 kp.theme.v1，
// 两个入口（侧栏按钮 / 设置页）通过 kp-theme-changed 自定义事件保持同步。

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { Role } from "./types";

export type Locale = "zh" | "en";
export type Motion = "on" | "off";

export interface DemoUser {
  name: string;
  role: Role;
}

const LOCALE_KEY = "kp.locale.v1";
const MOTION_KEY = "kp.motion.v1";
const USER_KEY = "kp.user.v1";

/* ---------------- 双语词典（框架文案；页面正文暂不迁移） ---------------- */

const dict = {
  zh: {
    "nav.chat": "问答",
    "nav.docs": "知识库",
    "nav.overview": "看板",
    "nav.permissions": "权限",
    "nav.audit": "审计",
    "nav.settings": "设置",
    "nav.admin": "管理",
    "nav.main": "主导航",
    "skip": "跳到主内容",
    "theme.light": "亮色",
    "theme.dark": "暗色",
    "theme.system": "跟随系统",
    "theme.aria": "主题：{label}，点击切换",
    "role.admin": "管理员",
    "role.manager": "经理",
    "role.employee": "员工",
  },
  en: {
    "nav.chat": "Chat",
    "nav.docs": "Library",
    "nav.overview": "Dashboard",
    "nav.permissions": "Permissions",
    "nav.audit": "Audit",
    "nav.settings": "Settings",
    "nav.admin": "Admin",
    "nav.main": "Main navigation",
    "skip": "Skip to content",
    "theme.light": "Light",
    "theme.dark": "Dark",
    "theme.system": "System",
    "theme.aria": "Theme: {label}, click to switch",
    "role.admin": "Admin",
    "role.manager": "Manager",
    "role.employee": "Employee",
  },
} as const;

export type DictKey = keyof (typeof dict)["zh"];

/* ---------------- Context ---------------- */

interface PrefsValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: DictKey) => string;
  motion: Motion;
  setMotion: (m: Motion) => void;
  user: DemoUser;
  setUser: (u: DemoUser) => void;
  resetUser: () => void;
}

const PrefsContext = createContext<PrefsValue | null>(null);

const DEFAULT_USER: DemoUser = { name: "演示用户", role: "employee" };

function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function PreferencesProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh");
  const [motion, setMotionState] = useState<Motion>("on");
  const [user, setUserState] = useState<DemoUser>(DEFAULT_USER);

  // 首次挂载从 localStorage 恢复（SSR 安全：读到再应用）
  useEffect(() => {
    const savedLocale = localStorage.getItem(LOCALE_KEY);
    if (savedLocale === "zh" || savedLocale === "en") setLocaleState(savedLocale);
    const savedMotion = localStorage.getItem(MOTION_KEY);
    if (savedMotion === "on" || savedMotion === "off") setMotionState(savedMotion);
    setUserState(readJSON<DemoUser>(USER_KEY, DEFAULT_USER));
  }, []);

  // 语言：同步 <html lang>
  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [locale]);

  // 动效：开关映射到 <html class="motion-off">（globals.css 覆盖 .rise/.slide-in）
  useEffect(() => {
    document.documentElement.classList.toggle("motion-off", motion === "off");
  }, [motion]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem(LOCALE_KEY, l);
  }, []);

  const setMotion = useCallback((m: Motion) => {
    setMotionState(m);
    localStorage.setItem(MOTION_KEY, m);
  }, []);

  const setUser = useCallback((u: DemoUser) => {
    setUserState(u);
    localStorage.setItem(USER_KEY, JSON.stringify(u));
  }, []);

  const resetUser = useCallback(() => {
    localStorage.removeItem(USER_KEY);
    setUserState(DEFAULT_USER);
  }, []);

  const t = useCallback(
    (key: DictKey) => dict[locale][key] ?? dict.zh[key] ?? key,
    [locale],
  );

  const value = useMemo<PrefsValue>(
    () => ({ locale, setLocale, t, motion, setMotion, user, setUser, resetUser }),
    [locale, setLocale, t, motion, setMotion, user, setUser, resetUser],
  );

  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): PrefsValue {
  const v = useContext(PrefsContext);
  if (!v) throw new Error("usePrefs must be used within PreferencesProvider");
  return v;
}

/** 角色徽章的语义色（演示身份标识） */
export const ROLE_BADGE: Record<Role, string> = {
  admin: "border-seal/40 text-seal",
  manager: "border-amber/40 text-amber",
  employee: "border-jade/40 text-jade",
};
