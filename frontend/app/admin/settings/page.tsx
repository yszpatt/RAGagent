"use client";

// 设置：外观 / 语言与动效 / 当前身份（演示）/ 本地数据。
// 全部为前端本机配置（localStorage），不涉及后端；
// 身份为演示性质，仅用于界面展示，真实权限以后端数据为准。

import { useDemoMode } from "@/lib/demo-context";
import {
  ROLE_BADGE,
  usePrefs,
  type Locale,
  type Motion,
} from "@/lib/prefs";
import { ThemeSegmented } from "@/components/theme-toggle";
import { PageHeader } from "@/components/ui/page";
import { Trash2, RotateCcw, RefreshCw, Server, IdCard } from "lucide-react";
import type { Role } from "@/lib/types";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-xl border border-line bg-paper p-4 shadow-sm">
      <h2 className="mb-3 text-sm font-medium text-ink">{title}</h2>
      {children}
    </section>
  );
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T;
  options: { key: T; label: string }[];
  onChange: (v: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex rounded-lg border border-line bg-porcelain p-0.5"
    >
      {options.map(({ key, label }) => (
        <button
          key={key}
          role="radio"
          aria-checked={value === key}
          onClick={() => onChange(key)}
          className={
            "rounded-[6px] px-3 py-1.5 text-xs transition-colors " +
            (value === key
              ? "bg-paper font-medium text-indigo-deep shadow-sm"
              : "text-ink-soft hover:text-ink")
          }
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export default function SettingsPage() {
  const { locale, setLocale, t, motion, setMotion, user, setUser, resetUser } =
    usePrefs();
  const { backend, refreshBackend } = useDemoMode();

  const roleOptions: { key: Role; label: string }[] = [
    { key: "admin", label: t("role.admin") },
    { key: "manager", label: t("role.manager") },
    { key: "employee", label: t("role.employee") },
  ];

  const backendText =
    backend === "up"
      ? locale === "zh"
        ? "已连接"
        : "Connected"
      : backend === "down"
        ? locale === "zh"
          ? "未连接（演示模式）"
          : "Offline (demo mode)"
        : locale === "zh"
          ? "检测中…"
          : "Probing…";

  return (
    <div className="mx-auto h-full w-full max-w-3xl space-y-4 overflow-y-auto">
      <PageHeader
        title={locale === "zh" ? "设置" : "Settings"}
        description={
          locale === "zh"
            ? "外观、语言与本机数据。所有配置仅保存在浏览器本地，不会上传。"
            : "Appearance, language and local data. Everything is stored locally in your browser."
        }
      />

      <Section title={locale === "zh" ? "外观" : "Appearance"}>
        <div className="flex items-center justify-between gap-4">
          <span className="text-xs text-ink-soft">
            {locale === "zh" ? "主题" : "Theme"}
          </span>
          <ThemeSegmented />
        </div>
      </Section>

      <Section title={locale === "zh" ? "语言与动效" : "Language & Motion"}>
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <span className="text-xs text-ink-soft">
              {locale === "zh" ? "界面语言" : "Language"}
            </span>
            <Segmented<Locale>
              ariaLabel={locale === "zh" ? "界面语言" : "Language"}
              value={locale}
              onChange={setLocale}
              options={[
                { key: "zh", label: "简体中文" },
                { key: "en", label: "English" },
              ]}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-xs text-ink-soft">
              {locale === "zh" ? "界面动效" : "Motion"}
            </span>
            <Segmented<Motion>
              ariaLabel={locale === "zh" ? "界面动效" : "Motion"}
              value={motion}
              onChange={setMotion}
              options={[
                { key: "on", label: locale === "zh" ? "开启" : "On" },
                { key: "off", label: locale === "zh" ? "关闭" : "Off" },
              ]}
            />
          </div>
          <p className="text-[11px] leading-4 text-ink-faint">
            {locale === "zh"
              ? "语言目前覆盖导航、侧栏与设置页等框架文案；页面正文将随版本逐步迁移。"
              : "Language currently covers framework texts (nav, sidebar, settings); page content will be migrated progressively."}
          </p>
        </div>
      </Section>

      <Section title={locale === "zh" ? "当前身份（演示）" : "Profile (demo)"}>
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="flex size-9 shrink-0 select-none items-center justify-center rounded-full bg-indigo-wash font-display text-sm font-bold text-indigo-deep"
            >
              {user.name.slice(0, 1)}
            </span>
            <div className="min-w-0 flex-1">
              <label
                htmlFor="demo-user-name"
                className="sr-only"
              >
                {locale === "zh" ? "姓名" : "Name"}
              </label>
              <input
                id="demo-user-name"
                value={user.name}
                onChange={(e) => setUser({ ...user, name: e.target.value })}
                placeholder={locale === "zh" ? "输入姓名" : "Your name"}
                className="w-full rounded-md border border-line bg-transparent px-2.5 py-1.5 text-sm text-ink placeholder:text-ink-faint focus:border-indigo/50 focus:outline-none"
              />
            </div>
            <span
              className={
                "shrink-0 rounded-sm border px-1.5 py-0.5 font-mono text-[10px] " +
                ROLE_BADGE[user.role]
              }
            >
              {roleOptions.find((r) => r.key === user.role)?.label}
            </span>
          </div>
          <div className="flex items-center justify-between gap-4">
            <span className="text-xs text-ink-soft">
              {locale === "zh" ? "角色" : "Role"}
            </span>
            <Segmented<Role>
              ariaLabel={locale === "zh" ? "角色" : "Role"}
              value={user.role}
              onChange={(role) => setUser({ ...user, role })}
              options={roleOptions}
            />
          </div>
          <p className="flex items-start gap-1.5 text-[11px] leading-4 text-ink-faint">
            <IdCard size={12} className="mt-0.5 shrink-0" />
            {locale === "zh"
              ? "演示身份仅保存在本机、用于界面展示；文档可见性与答案权限始终以后端数据为准。"
              : "Demo identity is local and for display only; access control always follows backend data."}
          </p>
        </div>
      </Section>

      <Section title={locale === "zh" ? "本地数据" : "Local data"}>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => {
              if (window.confirm(locale === "zh" ? "确认清除本机保存的会话记录？此操作不可恢复。" : "Clear locally stored conversations? This cannot be undone.")) {
                window.localStorage.removeItem("kp.conversations.v1");
                window.location.reload();
              }
            }}
            className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-soft transition-colors hover:border-seal/50 hover:text-seal"
          >
            <Trash2 size={13} />
            {locale === "zh" ? "清除本地会话记录" : "Clear local conversations"}
          </button>
          <button
            onClick={() => {
              if (window.confirm(locale === "zh" ? "恢复默认偏好（主题/语言/动效/身份）？" : "Reset preferences (theme/language/motion/identity)?")) {
                ["kp.theme.v1", "kp.locale.v1", "kp.motion.v1"].forEach((k) =>
                  window.localStorage.removeItem(k),
                );
                resetUser();
                window.location.reload();
              }
            }}
            className="flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs text-ink-soft transition-colors hover:border-seal/50 hover:text-seal"
          >
            <RotateCcw size={13} />
            {locale === "zh" ? "恢复默认偏好" : "Reset preferences"}
          </button>
        </div>
      </Section>

      <Section title={locale === "zh" ? "关于" : "About"}>
        <div className="space-y-2 text-xs text-ink-soft">
          <p className="flex items-center gap-1.5">
            <Server size={13} className="shrink-0" />
            {locale === "zh" ? "后端连接：" : "Backend: "}
            <span className={backend === "up" ? "text-jade" : backend === "down" ? "text-seal" : "text-ink-faint"}>
              {backendText}
            </span>
            <button
              onClick={() => void refreshBackend()}
              aria-label={locale === "zh" ? "重新检测后端" : "Re-probe backend"}
              className="ml-1 inline-flex items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-[11px] text-ink-soft hover:text-ink"
            >
              <RefreshCw size={11} />
              {locale === "zh" ? "重新检测" : "Re-probe"}
            </button>
          </p>
          <p>
            KnowledgePilot · {locale === "zh" ? "企业知识库问答 · 前端演示版" : "Enterprise KB Q&A · frontend demo"}
          </p>
        </div>
      </Section>
    </div>
  );
}
