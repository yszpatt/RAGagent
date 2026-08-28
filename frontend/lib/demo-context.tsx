"use client";

// 演示模式上下文：后端不可达时自动进入，也可手动切换。
// 演示模式下所有数据来自 lib/demo-data.ts（页面均带「演示/预览」标记）。

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { checkBackend } from "@/lib/api";

type BackendState = "probing" | "up" | "down";

interface DemoContextValue {
  /** 演示模式是否生效 */
  demo: boolean;
  backend: BackendState;
  /** 用户是否手动设置过模式（设置后不再自动切换） */
  toggleDemo: (on: boolean) => void;
  refreshBackend: () => void;
}

const DemoContext = createContext<DemoContextValue>({
  demo: false,
  backend: "probing",
  toggleDemo: () => {},
  refreshBackend: () => {},
});

const OVERRIDE_KEY = "kp.demo-override.v1";

export function DemoProvider({ children }: { children: React.ReactNode }) {
  const [backend, setBackend] = useState<BackendState>("probing");
  const [override, setOverride] = useState<boolean | null>(null);

  const probe = useCallback(async () => {
    const up = await checkBackend();
    setBackend(up ? "up" : "down");
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem(OVERRIDE_KEY);
    if (saved === "1") setOverride(true);
    else if (saved === "0") setOverride(false);
    void probe();
  }, [probe]);

  const toggleDemo = useCallback((on: boolean) => {
    setOverride(on);
    window.localStorage.setItem(OVERRIDE_KEY, on ? "1" : "0");
  }, []);

  const value = useMemo<DemoContextValue>(
    () => ({
      backend,
      demo: override ?? backend === "down",
      toggleDemo,
      refreshBackend: probe,
    }),
    [backend, override, toggleDemo, probe],
  );

  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemoMode(): DemoContextValue {
  return useContext(DemoContext);
}
