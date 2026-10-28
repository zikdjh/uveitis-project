import { request } from "@/api/client";

export type SummaryProtocol =
  | "openai_responses"
  | "openai_chat_completions"
  | "anthropic_messages";

export type SearchProvider =
  | "tavily"
  | "brave"
  | "serper"
  | "searxng"
  | "google_cse"
  | "bing"
  | "exa"
  | "perplexity";

export type IntegrationConfig = {
  summary_enabled: boolean;
  summary_protocol: SummaryProtocol;
  summary_base_url: string;
  summary_model: string;
  summary_api_key_configured: boolean;
  summary_api_key_hint: string;
  web_search_enabled: boolean;
  web_search_max_results: number;
  search_provider_order: SearchProvider[];
  tavily_api_key_configured: boolean;
  tavily_api_key_hint: string;
  brave_search_api_key_configured: boolean;
  brave_search_api_key_hint: string;
  serper_api_key_configured: boolean;
  serper_api_key_hint: string;
  google_cse_api_key_configured: boolean;
  google_cse_api_key_hint: string;
  google_cse_id: string;
  bing_search_api_key_configured: boolean;
  bing_search_api_key_hint: string;
  exa_api_key_configured: boolean;
  exa_api_key_hint: string;
  perplexity_api_key_configured: boolean;
  perplexity_api_key_hint: string;
  searxng_base_url: string;
  revision: number;
  updated_at: string | null;
  updated_by: string;
};

export type IntegrationUpdate = Partial<{
  summary_enabled: boolean;
  summary_protocol: SummaryProtocol;
  summary_base_url: string;
  summary_model: string;
  summary_api_key: string;
  clear_summary_api_key: boolean;
  web_search_enabled: boolean;
  web_search_max_results: number;
  search_provider_order: SearchProvider[];
  tavily_api_key: string;
  clear_tavily_api_key: boolean;
  brave_search_api_key: string;
  clear_brave_search_api_key: boolean;
  serper_api_key: string;
  clear_serper_api_key: boolean;
  google_cse_api_key: string;
  clear_google_cse_api_key: boolean;
  google_cse_id: string;
  bing_search_api_key: string;
  clear_bing_search_api_key: boolean;
  exa_api_key: string;
  clear_exa_api_key: boolean;
  perplexity_api_key: string;
  clear_perplexity_api_key: boolean;
  searxng_base_url: string;
  expected_revision: number;
}>;

export type IntegrationTestResult = {
  ok: boolean;
  detail: string;
  latency_ms: number;
  provider: string | null;
  attempts: number;
};

export type IntegrationTestBatchResult = {
  ok: boolean;
  succeeded: number;
  failed: number;
  skipped: number;
  items: IntegrationTestResult[];
};

export function getIntegrationConfig(): Promise<IntegrationConfig> {
  return request<IntegrationConfig>("/api/v1/admin/integrations");
}

export function updateIntegrationConfig(input: IntegrationUpdate): Promise<IntegrationConfig> {
  return request<IntegrationConfig>("/api/v1/admin/integrations", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function testIntegration(input: {
  kind: "summary" | "search";
  provider?: SearchProvider;
  query?: string;
}): Promise<IntegrationTestResult> {
  return request<IntegrationTestResult>("/api/v1/admin/integrations/test", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function testSearchProviders(input: {
  providers: SearchProvider[];
  query?: string;
}): Promise<IntegrationTestBatchResult> {
  return request<IntegrationTestBatchResult>(
    "/api/v1/admin/integrations/test-search-batch",
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}
