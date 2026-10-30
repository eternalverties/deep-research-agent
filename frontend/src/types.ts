export type ResearchStatusValue = "running" | "interrupted" | "completed" | "error";

export interface ReportSection {
  heading: string;
  content: string;
  citations: string[];
}

export interface Citation {
  title: string;
  url: string;
}

export interface Report {
  summary: string;
  sections: ReportSection[];
  citations: Citation[];
}

export interface Evidence {
  evidence_id: string;
  source_url: string;
  source_title: string;
  quote: string;
  score: number;
}

export type ClaimStatus = "supported" | "contradicted" | "insufficient";

export interface Claim {
  claim_id: string;
  content: string;
  cited_urls: string[];
  status: ClaimStatus;
  confidence: number;
  evidence_ids: string[];
  reason: string;
}

export interface VerificationSummary {
  supported: number;
  contradicted: number;
  insufficient: number;
  total: number;
  coverage: number;
  error?: string;
}

export interface TraceEvent {
  node: string;
  status: string;
  started_at: number;
  duration_ms: number;
  iteration: number;
  llm_calls: number;
  detail: string;
}

export interface InterruptPayload {
  type?: string;
  message?: string;
  query?: string;
  proposed_subtasks?: string[];
}

export interface ResearchStatus {
  thread_id: string;
  status: ResearchStatusValue;
  report: Report | null;
  guardrail_flags: string[];
  llm_calls: number | null;
  iterations: number | null;
  repairs: number | null;
  verification: VerificationSummary | null;
  claims: Claim[] | null;
  evidence: Evidence[] | null;
  trace: TraceEvent[] | null;
  search_provider: string | null;
  infrastructure_error: string | null;
  error: string | null;
  interrupt: InterruptPayload | null;
}

export interface ResearchAccepted {
  thread_id: string;
  status: string;
}

export interface ResumeDecision {
  action: "approve" | "edit" | "reject" | "abort";
  subtasks?: string[];
  feedback?: string;
  reason?: string;
}
