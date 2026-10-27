import { request } from "@/api/client";

export type DictionaryValueType =
  | "string"
  | "int"
  | "float"
  | "bool"
  | "json"
  | "secret";

export type DataDictionaryEntry = {
  id: string;
  namespace: string;
  key: string;
  value_type: DictionaryValueType;
  value: unknown;
  configured: boolean;
  is_secret: boolean;
  description: string;
  revision: number;
  created_at: string | null;
  updated_at: string | null;
  updated_by: string;
};

export function listDataDictionary(params?: {
  namespace?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<DataDictionaryEntry[]> {
  const query = new URLSearchParams();
  if (params?.namespace) query.set("namespace", params.namespace);
  if (params?.search) query.set("search", params.search);
  if (params?.limit) query.set("limit", String(params.limit));
  if (params?.offset) query.set("offset", String(params.offset));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<DataDictionaryEntry[]>(
    `/api/v1/admin/data-dictionary${suffix}`,
  );
}
