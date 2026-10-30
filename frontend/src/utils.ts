export function safeUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

export function hostname(value: string): string {
  const url = safeUrl(value);
  if (!url) return value;
  try {
    return new URL(url).hostname;
  } catch {
    return value;
  }
}

export function formatDuration(ms: number): string {
  const value = Math.max(0, Number(ms) || 0);
  if (value < 1000) return `${Math.round(value)}ms`;
  const total = Math.floor(value / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

export function statusLabel(status: string): string {
  return (
    {
      running: "研究中",
      interrupted: "等待审批",
      completed: "已完成",
      error: "出错",
    }[status] ?? status
  );
}
