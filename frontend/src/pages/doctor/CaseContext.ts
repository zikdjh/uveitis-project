import { createContext } from "react";

import type { CaseRecord } from "@/api/cases";

export type CaseContextValue = {
  item: CaseRecord;
  setItem: (item: CaseRecord) => void;
};

export const CaseContext = createContext<CaseContextValue | null>(null);
