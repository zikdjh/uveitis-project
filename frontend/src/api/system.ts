import { request } from "@/api/client";

export type ModelService = {
  role: string;
  name: string;
  status: "mock" | "configured" | "offline";
  required: boolean;
  enabled: boolean;
  endpoint: string;
};

export type SystemOverview = {
  stats: {
    total: number;
    analyzing: number;
    awaiting_review: number;
    reviewed: number;
  };
  model_mode: "mock" | "remote";
  models: ModelService[];
  disclaimer: string;
};

export function getSystemOverview(): Promise<SystemOverview> {
  return request<SystemOverview>("/api/v1/system/overview");
}
