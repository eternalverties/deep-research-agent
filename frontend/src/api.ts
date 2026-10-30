import type {
  ResearchAccepted,
  ResearchStatus,
  ResumeDecision,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    let detail = `请求失败（HTTP ${response.status}）`;
    try {
      const data = (await response.json()) as { detail?: string };
      detail = data.detail ?? detail;
    } catch {
      // keep the generic message
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  start: (query: string) =>
    request<ResearchAccepted>("/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    }),
  status: (threadId: string) =>
    request<ResearchStatus>(`/research/${encodeURIComponent(threadId)}`),
  resume: (threadId: string, decision: ResumeDecision) =>
    request<ResearchAccepted>(
      `/research/${encodeURIComponent(threadId)}/resume`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decision),
      },
    ),
};
