// 时间戳统一渲染：演示数据基于 Date.now() 构造，SSR 与客户端水合存在分钟级偏差，
// suppressHydrationWarning 由客户端值收敛，避免 hydration 告警。

export function Time({
  ms,
  className,
}: {
  ms: number;
  className?: string;
}) {
  const pad = (n: number) => String(n).padStart(2, "0");
  const d = new Date(ms);
  const label = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return (
    <time dateTime={d.toISOString()} suppressHydrationWarning className={className}>
      {label}
    </time>
  );
}
