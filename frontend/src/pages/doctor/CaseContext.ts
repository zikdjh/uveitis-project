import { createContext } from "react";

import type { AnalysisJobRecord, CaseRecord } from "@/api/cases";

export type CaseContextValue = {
  item: CaseRecord;
  setItem: (item: CaseRecord) => void;
  analysisJob: AnalysisJobRecord | null;
  setAnalysisJob: (job: AnalysisJobRecord | null) => void;
};

export const CaseContext = createContext<CaseContextValue | null>(null);
