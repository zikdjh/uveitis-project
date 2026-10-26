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
  confidence: number;
  safety_flags: string[];
  started_at: string;
  completed_at: string | null;
  error: string;
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

export function listCases(): Promise<CaseRecord[]> {
  return request<CaseRecord[]>("/api/v1/cases");
}

export function getCase(caseId: string): Promise<CaseRecord> {
  return request<CaseRecord>(`/api/v1/cases/${caseId}`);
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
