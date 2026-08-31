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

/** 向量化（embedding）提供方配置：本地 sentence-transformers 或 Ollama /api/embed。 */
export type EmbeddingProviderName = "local" | "ollama";
export interface EmbeddingPref {
  provider: EmbeddingProviderName;
  ip: string; // Ollama 主机 IP（provider=ollama 时生效）
  port: string; // Ollama 端口，默认 11434
  model: string; // 模型名，默认 bge-m3
}

const LOCALE_KEY = "kp.locale.v1";
const MOTION_KEY = "kp.motion.v1";
const USER_KEY = "kp.user.v1";
const EMBEDDING_KEY = "kp.embedding.v1";

export const DEFAULT_EMBEDDING: EmbeddingPref = {
  provider: "ollama",
  ip: "192.168.9.26",
  port: "11434",
  model: "bge-m3",
};

/** 读取 embedding 配置并向请求注入 X-KP-Embedding-Cfg 头（仅 ollama 时附加）。 */
export function embeddingHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(EMBEDDING_KEY);
    if (!raw) return {};
    const cfg = { ...DEFAULT_EMBEDDING, ...(JSON.parse(raw) as Partial<EmbeddingPref>) };
    if (cfg.provider !== "ollama") return {};
    const url = `http://${cfg.ip || "localhost"}:${cfg.port || "11434"}`;
    return {
      "X-KP-Embedding-Cfg": JSON.stringify({
        provider: "ollama",
        ollama_url: url,
        model: cfg.model || "bge-m3",
      }),
    };
  } catch {
    return {};
  }
}

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
    /* 聊天页 / 会话面板 */
    "chat.newConv": "新会话",
    "chat.sessions": "会话",
    "chat.previewTag": "演示模式",
    "chat.localNote": "提问后会自动保存在本机，此列表不会上传。",
    "chat.turnsSuffix": "{n}轮",
    "chat.demoNote": "演示会话不占用本机存储。",
    "chat.rounds": "{n} 轮问答",
    "chat.noTitle": "（无标题会话）",
    "chat.loadFailed": "加载会话失败",
    "chat.askError": "请求出错",
    "chat.askErrorHint":
      "。请确认后端已启动（uvicorn app.main:app），或在左下角开启演示模式。",
    "chat.welcomeTitle": "问一个业务问题，答案必带出处",
    "chat.welcomeDesc":
      "系统在已上传的知识库中检索并生成答案，每条结论都标注来源页码；检索不到的内容会明确告知，不编造。",
    "chat.demoBanner": "后端未连接，当前为演示数据。去",
    "chat.uploadFirst": "上传文档后即可真实问答。",
    "chat.generating": "检索知识库并生成答案…",
    "chat.inputLabel": "输入问题",
    "chat.placeholder": "例如：供应商合同里违约金是怎么约定的？",
    "chat.inputHint": "Enter 发送 · Shift+Enter 换行 · 答案均标注来源页码",
    "chat.send": "提问",
    "chat.viewSources": "查看来源案卷",
    "chat.pageNum": "第 {n} 页",
    "chat.pageUnknown": "页码未知",
    "chat.roundAria": "第 {n} 轮问答",
    "chat.q": "问",
    "chat.a": "答",
    "chat.demoBadge": "演示",
    "chat.noAnswer": "可换个问法，或先到「知识库」上传相关文档。",
    "chat.sources": "来源",
    "chat.refPrefix": "引-",
    "chat.demoDoc": "演示文档.pdf",
    "chat.demoExcerpt": "（演示数据未收录该片段原文）",
    "chat.kbRef": "知识库引用",
    "chat.sourceDock": "来源案卷",
    "chat.fieldDoc": "文档",
    "chat.fieldPage": "页码",
    "chat.fieldSection": "章节",
    "chat.verified": "已核实",
    "chat.excerptUnavailable": "原文摘录暂不可展示：后端尚未提供引用内容查询接口",
    "chat.excerptPlan": "（规划中 {api}）。当前可核对的信息：文档名与页码。",
    "chat.viewSourceRef": "查看来源 {n}",
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
    /* Chat page / conversation panel */
    "chat.newConv": "New chat",
    "chat.sessions": "Conversations",
    "chat.previewTag": "Demo mode",
    "chat.localNote": "Questions are saved locally; this list never leaves your device.",
    "chat.turnsSuffix": "{n} turns",
    "chat.demoNote": "Demo conversations are not stored.",
    "chat.rounds": "{n} rounds",
    "chat.noTitle": "(Untitled conversation)",
    "chat.loadFailed": "Failed to load conversation",
    "chat.askError": "Request failed",
    "chat.askErrorHint":
      ". Make sure the backend is running (uvicorn app.main:app), or enable demo mode at the bottom-left.",
    "chat.welcomeTitle": "Ask a business question — answers come with sources",
    "chat.welcomeDesc":
      "Answers are generated from your uploaded library; every claim cites a page number. Missing content is stated explicitly, never fabricated.",
    "chat.demoBanner": "Backend offline — showing demo data. Go to",
    "chat.uploadFirst": "Upload documents to enable real Q&A.",
    "chat.generating": "Searching library and composing answer…",
    "chat.inputLabel": "Ask a question",
    "chat.placeholder": "e.g. What does the supplier contract say about penalties?",
    "chat.inputHint": "Enter to send · Shift+Enter for newline · answers cite page numbers",
    "chat.send": "Ask",
    "chat.viewSources": "View source docket",
    "chat.pageNum": "Page {n}",
    "chat.pageUnknown": "Page unknown",
    "chat.roundAria": "Round {n}",
    "chat.q": "Q",
    "chat.a": "A",
    "chat.demoBadge": "Demo",
    "chat.noAnswer": "Try rephrasing, or upload related documents to the Library first.",
    "chat.sources": "Sources",
    "chat.refPrefix": "Ref-",
    "chat.demoDoc": "demo-document.pdf",
    "chat.demoExcerpt": "(Demo data doesn't include this excerpt)",
    "chat.kbRef": "Knowledge base reference",
    "chat.sourceDock": "Source docket",
    "chat.fieldDoc": "Document",
    "chat.fieldPage": "Page",
    "chat.fieldSection": "Section",
    "chat.verified": "Verified",
    "chat.excerptUnavailable":
      "Excerpt unavailable: the backend citation-content API is not yet provided",
    "chat.excerptPlan":
      "(planned {api}). Currently you can verify: document name and page.",
    "chat.viewSourceRef": "View source {n}",
  },
} as const;

export type DictKey = keyof (typeof dict)["zh"];

/* ---------------- Context ---------------- */

interface PrefsValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  /** 取词典文案；{key} 形式占位符由 vars 插值 */
  t: (key: DictKey, vars?: Record<string, string | number>) => string;
  motion: Motion;
  setMotion: (m: Motion) => void;
  user: DemoUser;
  setUser: (u: DemoUser) => void;
  resetUser: () => void;
  embedding: EmbeddingPref;
  setEmbedding: (e: EmbeddingPref) => void;
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
  const [embedding, setEmbeddingState] = useState<EmbeddingPref>(DEFAULT_EMBEDDING);

  // 首次挂载从 localStorage 恢复（SSR 安全：读到再应用）
  useEffect(() => {
    const savedLocale = localStorage.getItem(LOCALE_KEY);
    if (savedLocale === "zh" || savedLocale === "en") setLocaleState(savedLocale);
    const savedMotion = localStorage.getItem(MOTION_KEY);
    if (savedMotion === "on" || savedMotion === "off") setMotionState(savedMotion);
    setUserState(readJSON<DemoUser>(USER_KEY, DEFAULT_USER));
    setEmbeddingState(readJSON<EmbeddingPref>(EMBEDDING_KEY, DEFAULT_EMBEDDING));
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

  const setEmbedding = useCallback((e: EmbeddingPref) => {
    setEmbeddingState(e);
    localStorage.setItem(EMBEDDING_KEY, JSON.stringify(e));
  }, []);

  const t = useCallback(
    (key: DictKey, vars?: Record<string, string | number>) => {
      let s: string = dict[locale][key] ?? dict.zh[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          s = s.replaceAll(`{${k}}`, String(v));
        }
      }
      return s;
    },
    [locale],
  );

  const value = useMemo<PrefsValue>(
    () => ({ locale, setLocale, t, motion, setMotion, user, setUser, resetUser, embedding, setEmbedding }),
    [locale, setLocale, t, motion, setMotion, user, setUser, resetUser, embedding, setEmbedding],
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
