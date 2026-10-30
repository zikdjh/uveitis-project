import { authorizedFetch, readErrorMessage, request } from "@/api/client";

export type CaseStatus = "created" | "analyzing" | "awaiting_review" | "reviewed" | "failed";
export type ImageKind = "fundus" | "ultrawide" | "oct" | "anterior" | "other";

export type CaseImage = {
  id: string;
  filename: string;
  kind: ImageKind;
  content_type: string;
  size_bytes: number;
  url: string;
};

export type PipelineStage = {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "skipped" | "failed";
  detail: string;
};

export type ComponentResult = {
  key: string;
  label: string;
  status: PipelineStage["status"];
  detail: string;
  latency_ms: number;
};

export type AnalysisResult = {
  status: "queued" | "running" | "completed" | "failed";
  model_mode: "mock" | "remote";
  stages: PipelineStage[];
  findings: Array<{ label: string; location: string; confidence: number }>;
  impression: string;
  differential: Array<{ label: string; confidence: number }>;
  urgency: "unknown" | "low" | "medium" | "high";
  recommendations: string[];
  evidence: Array<{ id: string; source: string; snippet: string; score: number }>;
  web_evidence: Array<{
    title: string;
    url: string;
    snippet: string;
    provider: string;
    score: number | null;
  }>;
  component_results: ComponentResult[];
  summary: string;
  external_summary_used: boolean;
  external_payload: Record<string, unknown>;
  toolchain_plan: {
    planner: string;
    steps: string[];
    skipped: Record<string, string>;
    rationale: string;
    notes: string[];
  };
  confidence: number;
  safety_flags: string[];
  started_at: string;
  completed_at: string | null;
  error: string;
};

export type AnalysisJobRecord = {
  id: number;
  case_id: string;
  status: "queued" | "running" | "finalizing" | "completed" | "failed";
  attempt_count: number;
  max_attempts: number;
  error: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type AnalysisQueueRecord = {
  job_id: string;
  case_id: string;
  owner_name: string;
  complaint: string;
  patient_age: number | null;
  patient_sex: string;
  case_status: string;
  job_status: "queued" | "running" | "finalizing" | "completed" | "failed";
  attempt_count: number;
  max_attempts: number;
  error: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type CaseReview = {
  decision: "accepted" | "modified" | "rejected";
  final_impression: string;
  note: string;
  reviewer: string;
  reviewed_at: string;
};

export type CaseRecord = {
  id: string;
  owner_id: string;
  owner_name: string;
  patient_age: number;
  patient_sex: "F" | "M" | "U";
  complaint: string;
  medical_history: string;
  affected_eye: "OD" | "OS" | "OU" | "UNKNOWN";
  consent_confirmed: boolean;
  status: CaseStatus;
  images: CaseImage[];
  analysis: AnalysisResult | null;
  review: CaseReview | null;
  created_at: string;
  updated_at: string;
};

export type CaseListPage = {
  items: CaseRecord[];
  total: number;
  page: number;
  page_size: number;
};

export type CaseListQuery = {
  page?: number;
  page_size?: number;
  status?: CaseStatus;
  from?: string;
  to?: string;
};

export type CaseCreateInput = {
  patient_age: number;
  patient_sex: "F" | "M" | "U";
  complaint: string;
  medical_history: string;
  affected_eye: "OD" | "OS" | "OU" | "UNKNOWN";
  consent_confirmed: boolean;
};

export type ReviewInput = {
  decision: "accepted" | "modified" | "rejected";
  final_impression: string;
  note: string;
  reviewer: string;
};

function parseCaseListPage(value: unknown): CaseListPage {
  if (!value || typeof value !== "object") {
    throw new Error("病例列表响应格式异常，请刷新后重试");
  }
  const candidate = value as Partial<CaseListPage>;
  if (
    !Array.isArray(candidate.items)
    || typeof candidate.total !== "number"
    || typeof candidate.page !== "number"
    || typeof candidate.page_size !== "number"
  ) {
    throw new Error("病例列表响应格式异常，请刷新后重试");
  }
  return {
    items: candidate.items.map((item) => ({
      ...item,
      images: Array.isArray(item.images) ? item.images : [],
      analysis: item.analysis ?? null,
      review: item.review ?? null,
    })),
    total: candidate.total,
    page: candidate.page,
    page_size: candidate.page_size,
  };
}

export async function listCases(query: CaseListQuery = {}): Promise<CaseListPage> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const suffix = params.size ? `?${params.toString()}` : "";
  return parseCaseListPage(await request<unknown>(`/api/v1/cases${suffix}`));
}

export function getCase(caseId: string): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/v1/cases/${caseId}`);
}

export function getAnalysisJob(caseId: string): Promise<AnalysisJobRecord | null> {
  return request<AnalysisJobRecord | null>(`/api/v1/cases/${caseId}/analysis-job`);
}

export function listAnalysisJobs(limit = 50): Promise<AnalysisQueueRecord[]> {
  return request<AnalysisQueueRecord[]>(`/api/v1/cases/analysis-jobs?limit=${limit}`);
}

export function createCase(input: CaseCreateInput): Promise<CaseRecord> {
  return request<CaseRecord>("/api/v1/cases", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function uploadCaseImages(
  caseId: string,
  files: File[],
  kind: ImageKind,
): Promise<CaseRecord> {
  const body = new FormData();
  body.append("kind", kind);
  files.forEach((file) => body.append("files", file));
  const response = await authorizedFetch(`/api/v1/cases/${caseId}/images`, {
    method: "POST",
    body,
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.json() as Promise<CaseRecord>;
}

export function analyzeCase(caseId: string): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/v1/cases/${caseId}/analyze`, { method: "POST" });
}

export function reviewCase(caseId: string, input: ReviewInput): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/v1/cases/${caseId}/review`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}
