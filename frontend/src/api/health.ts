import { request } from "@/api/client";

export type HealthStatus = {
  status: string;
  service: string;
  version: string;
  environment: string;
  ready: boolean;
};

export function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/api/v1/health");
}
