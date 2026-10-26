import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Globe2,
  KeyRound,
  LoaderCircle,
  PlugZap,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  getIntegrationConfig,
  testIntegration,
  updateIntegrationConfig,
  type IntegrationConfig,
  type IntegrationUpdate,
  type SearchProvider,
  type SummaryProtocol,
} from "@/api/integrations";

const providerOrderSeed: SearchProvider[] = [
  "tavily",
  "brave",
  "serper",
  "google_cse",
  "bing",
  "exa",
  "perplexity",
  "searxng",
];

type SecretField =
  | "summary_api_key"
  | "tavily_api_key"
  | "brave_search_api_key"
  | "serper_api_key"
  | "google_cse_api_key"
  | "bing_search_api_key"
  | "exa_api_key"
  | "perplexity_api_key";

type ProviderDescriptor = {
  id: SearchProvider;
  name: string;
  detail: string;
  secret?: SecretField;
  configuredField?: keyof IntegrationConfig;
  hintField?: keyof IntegrationConfig;
};

const providers: ProviderDescriptor[] = [
  {
    id: "tavily",
    name: "Tavily",
    detail: "研究型检索",
    secret: "tavily_api_key",
    configuredField: "tavily_api_key_configured",
    hintField: "tavily_api_key_hint",
  },
  {
    id: "brave",
    name: "Brave Search",
    detail: "独立索引",
    secret: "brave_search_api_key",
    configuredField: "brave_search_api_key_configured",
    hintField: "brave_search_api_key_hint",
  },
  {
    id: "serper",
    name: "Serper",
    detail: "Google 结果接口",
    secret: "serper_api_key",
    configuredField: "serper_api_key_configured",
    hintField: "serper_api_key_hint",
  },
  {
    id: "google_cse",
    name: "Google CSE",
    detail: "可编程搜索",
    secret: "google_cse_api_key",
    configuredField: "google_cse_api_key_configured",
    hintField: "google_cse_api_key_hint",
  },
  {
    id: "bing",
    name: "Bing Web Search",
    detail: "网页检索",
    secret: "bing_search_api_key",
    configuredField: "bing_search_api_key_configured",
    hintField: "bing_search_api_key_hint",
  },
  {
    id: "exa",
    name: "Exa",
    detail: "语义搜索",
    secret: "exa_api_key",
    configuredField: "exa_api_key_configured",
    hintField: "exa_api_key_hint",
  },
  {
    id: "perplexity",
    name: "Perplexity",
    detail: "带引用答案",
    secret: "perplexity_api_key",
    configuredField: "perplexity_api_key_configured",
    hintField: "perplexity_api_key_hint",
  },
  {
    id: "searxng",
    name: "SearXNG",
    detail: "自建元搜索",
  },
];

const secretFields: SecretField[] = [
  "summary_api_key",
  "tavily_api_key",
  "brave_search_api_key",
  "serper_api_key",
  "google_cse_api_key",
  "bing_search_api_key",
  "exa_api_key",
  "perplexity_api_key",
];

const clearFieldBySecret = {
  summary_api_key: "clear_summary_api_key",
  tavily_api_key: "clear_tavily_api_key",
  brave_search_api_key: "clear_brave_search_api_key",
  serper_api_key: "clear_serper_api_key",
  google_cse_api_key: "clear_google_cse_api_key",
  bing_search_api_key: "clear_bing_search_api_key",
  exa_api_key: "clear_exa_api_key",
  perplexity_api_key: "clear_perplexity_api_key",
} as const;

type Draft = {
  summaryEnabled: boolean;
  summaryProtocol: SummaryProtocol;
  summaryBaseUrl: string;
  summaryModel: string;
  summaryIncludeClinicalText: boolean;
  webSearchEnabled: boolean;
  webSearchIncludeComplaint: boolean;
  webSearchMaxResults: number;
  googleCseId: string;
  searxngBaseUrl: string;
  secrets: Record<SecretField, string>;
  clearSecrets: Record<SecretField, boolean>;
  providerOrder: SearchProvider[];
  providerEnabled: Record<SearchProvider, boolean>;
};

const protocolLabels: Record<SummaryProtocol, string> = {
  openai_responses: "OpenAI Responses",
  openai_chat_completions: "OpenAI Chat Completions",
  anthropic_messages: "Anthropic Messages",
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function completeProviderOrder(order: SearchProvider[]): SearchProvider[] {
  const unique = [...new Set(order)].filter((item) =>
    providerOrderSeed.includes(item),
  );
  return [...unique, ...providerOrderSeed.filter((item) => !unique.includes(item))];
}

function emptySecretDraft<T extends string | boolean>(value: T) {
  return Object.fromEntries(secretFields.map((field) => [field, value])) as Record<
    SecretField,
    T
  >;
}

function emptyProviderFlags(value: boolean) {
  return Object.fromEntries(
    providerOrderSeed.map((provider) => [provider, value]),
  ) as Record<SearchProvider, boolean>;
}

function draftFromConfig(config: IntegrationConfig): Draft {
  const providerOrder = completeProviderOrder(config.search_provider_order);
  const enabled = emptyProviderFlags(false);
  for (const provider of providerOrder) enabled[provider] = true;
  return {
    summaryEnabled: config.summary_enabled,
    summaryProtocol: config.summary_protocol,
    summaryBaseUrl: config.summary_base_url,
    summaryModel: config.summary_model,
    summaryIncludeClinicalText: config.summary_include_clinical_text,
    webSearchEnabled: config.web_search_enabled,
    webSearchIncludeComplaint: config.web_search_include_complaint,
    webSearchMaxResults: config.web_search_max_results,
    googleCseId: config.google_cse_id,
    searxngBaseUrl: config.searxng_base_url,
    secrets: emptySecretDraft(""),
    clearSecrets: emptySecretDraft(false),
    providerOrder,
    providerEnabled: enabled,
  };
}

function buildUpdate(draft: Draft, revision: number): IntegrationUpdate {
  const payload: IntegrationUpdate = {
    summary_enabled: draft.summaryEnabled,
    summary_protocol: draft.summaryProtocol,
    summary_base_url: draft.summaryBaseUrl.trim(),
    summary_model: draft.summaryModel.trim(),
    summary_include_clinical_text: draft.summaryIncludeClinicalText,
    web_search_enabled: draft.webSearchEnabled,
    web_search_include_complaint: draft.webSearchIncludeComplaint,
    web_search_max_results: draft.webSearchMaxResults,
    google_cse_id: draft.googleCseId.trim(),
    searxng_base_url: draft.searxngBaseUrl.trim(),
    search_provider_order: draft.providerOrder.filter(
      (provider) => draft.providerEnabled[provider],
    ),
    expected_revision: revision,
  };
  const dynamicPayload = payload as Record<string, unknown>;
  for (const field of secretFields) {
    const value = draft.secrets[field].trim();
    if (value) dynamicPayload[field] = value;
    if (draft.clearSecrets[field]) {
      dynamicPayload[clearFieldBySecret[field]] = true;
    }
  }
  return payload;
}

function isProviderConfigured(
  config: IntegrationConfig,
  provider: ProviderDescriptor,
) {
  if (provider.id === "searxng") return Boolean(config.searxng_base_url.trim());
  const configured = provider.configuredField
    ? Boolean(config[provider.configuredField])
    : false;
  if (provider.id === "google_cse") {
    return configured && Boolean(config.google_cse_id.trim());
  }
  return configured;
}

export default function ServicesPage() {
  const [config, setConfig] = useState<IntegrationConfig | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const configuredProviders = useMemo(
    () =>
      config
        ? providers.filter((provider) => isProviderConfigured(config, provider))
            .length
        : 0,
    [config],
  );

  async function load() {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const loaded = await getIntegrationConfig();
      setConfig(loaded);
      setDraft(draftFromConfig(loaded));
      setDirty(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "服务配置加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function changeDraft(updater: (current: Draft) => Draft) {
    setDraft((current) => (current ? updater(current) : current));
    setDirty(true);
    setNotice(null);
  }

  function setSecret(field: SecretField, value: string) {
    changeDraft((current) => ({
      ...current,
      secrets: { ...current.secrets, [field]: value },
    }));
  }

  function setClearSecret(field: SecretField, checked: boolean) {
    changeDraft((current) => ({
      ...current,
      secrets: checked
        ? { ...current.secrets, [field]: "" }
        : current.secrets,
      clearSecrets: { ...current.clearSecrets, [field]: checked },
    }));
  }

  function moveProvider(index: number, direction: -1 | 1) {
    changeDraft((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.providerOrder.length) return current;
      const providerOrder = [...current.providerOrder];
      [providerOrder[index], providerOrder[target]] = [
        providerOrder[target],
        providerOrder[index],
      ];
      return { ...current, providerOrder };
    });
  }

  async function persistDraft(showNotice = true) {
    if (!draft || !config) return null;
    setSaving(true);
    setError(null);
    if (showNotice) setNotice(null);
    try {
      const updated = await updateIntegrationConfig(
        buildUpdate(draft, config.revision),
      );
      setConfig(updated);
      setDraft(draftFromConfig(updated));
      setDirty(false);
      if (showNotice) setNotice(`配置已保存，版本 ${updated.revision}。`);
      return updated;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "服务配置保存失败");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function checkSummary() {
    if (dirty && !(await persistDraft(false))) return;
    setTesting("summary");
    setError(null);
    setNotice(null);
    try {
      const result = await testIntegration({ kind: "summary" });
      if (!result.ok) throw new Error(result.detail);
      setNotice(`${result.detail}，耗时 ${result.latency_ms} ms。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部总结检查失败");
    } finally {
      setTesting(null);
    }
  }

  async function checkProvider(provider: SearchProvider) {
    if (dirty && !(await persistDraft(false))) return;
    setTesting(provider);
    setError(null);
    setNotice(null);
    try {
      const result = await testIntegration({
        kind: "search",
        provider,
        query: "uveitis clinical guideline",
      });
      if (!result.ok) throw new Error(result.detail);
      setNotice(`${result.detail}，耗时 ${result.latency_ms} ms。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "搜索服务检查失败");
    } finally {
      setTesting(null);
    }
  }

  if (loading && !config) {
    return (
      <section className="page">
        <div className="panel loading-panel">
          <LoaderCircle className="spin" size={22} />
          <span>正在读取服务配置</span>
        </div>
      </section>
    );
  }

  if (!config || !draft) {
    return (
      <section className="page">
        <div className="page-heading">
          <div><h1>服务配置</h1></div>
          <button className="button secondary" type="button" onClick={() => void load()}>
            <RefreshCw size={16} /> 重新读取
          </button>
        </div>
        <div className="notice error-notice" role="alert">
          <AlertCircle size={17} /> {error ?? "服务配置不可用"}
        </div>
      </section>
    );
  }

  const summaryConfigured =
    config.summary_api_key_configured &&
    Boolean(config.summary_base_url.trim()) &&
    Boolean(config.summary_model.trim());
  const summaryActive = summaryConfigured && draft.summaryEnabled;
  const searchActive = draft.webSearchEnabled;

  return (
    <section className="page integration-page">
      <div className="page-heading">
        <div>
          <h1>服务配置</h1>
          <p className="page-lead">外部模型与网络搜索凭据由管理员统一维护。</p>
        </div>
        <div className="heading-actions">
          <button
            className="button secondary"
            type="button"
            onClick={() => void load()}
            disabled={loading || saving || testing !== null}
          >
            <RefreshCw size={16} className={loading ? "spin" : ""} /> 重新读取
          </button>
          <button
            className="button primary"
            type="button"
            onClick={() => void persistDraft()}
            disabled={saving || testing !== null}
          >
            {saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}
            {saving ? "保存中" : "保存配置"}
          </button>
        </div>
      </div>

      <div className="integration-status-strip">
        <div>
          <span className={`status-dot ${summaryActive ? "online" : "offline"}`} />
          <span>外部总结</span>
          <strong>{summaryConfigured ? "已配置" : "未完成"}</strong>
        </div>
        <div>
          <span className={`status-dot ${searchActive ? "online" : "offline"}`} />
          <span>网络搜索</span>
          <strong>{configuredProviders} / {providers.length} 家</strong>
        </div>
        <div>
          <ShieldCheck size={15} />
          <span>配置版本</span>
          <strong>v{config.revision}</strong>
        </div>
        {config.updated_at && (
          <time dateTime={config.updated_at}>
            {dateFormatter.format(new Date(config.updated_at))}
          </time>
        )}
      </div>

      {error && (
        <div className="notice error-notice" role="alert">
          <AlertCircle size={17} /> {error}
        </div>
      )}
      {notice && (
        <div className="notice success-notice">
          <CheckCircle2 size={17} /> {notice}
        </div>
      )}
      {dirty && !error && (
        <div className="notice draft-notice">
          <span className="draft-dot" /> 当前修改尚未保存
        </div>
      )}

      <section className="panel integration-section">
        <div className="section-heading integration-section-heading">
          <div>
            <span className="section-kicker"><Sparkles size={14} /> 外部模型</span>
            <h2>总结 API</h2>
            <span>{protocolLabels[draft.summaryProtocol]}</span>
          </div>
          <button
            className="button secondary compact-button"
            type="button"
            onClick={() => void checkSummary()}
            disabled={saving || testing !== null}
          >
            {testing === "summary" ? <LoaderCircle className="spin" size={15} /> : <PlugZap size={15} />}
            {testing === "summary" ? "检查中" : "检查配置"}
          </button>
        </div>

        <div className="integration-field-grid">
          <label>
            接口协议
            <select
              value={draft.summaryProtocol}
              onChange={(event) => changeDraft((current) => ({
                ...current,
                summaryProtocol: event.target.value as SummaryProtocol,
              }))}
            >
              {(Object.keys(protocolLabels) as SummaryProtocol[]).map((protocol) => (
                <option value={protocol} key={protocol}>{protocolLabels[protocol]}</option>
              ))}
            </select>
          </label>
          <label>
            模型名称
            <input
              value={draft.summaryModel}
              onChange={(event) => changeDraft((current) => ({
                ...current,
                summaryModel: event.target.value,
              }))}
              maxLength={200}
              autoComplete="off"
              placeholder="model-id"
            />
          </label>
          <label className="span-2">
            API 地址
            <input
              value={draft.summaryBaseUrl}
              onChange={(event) => changeDraft((current) => ({
                ...current,
                summaryBaseUrl: event.target.value,
              }))}
              type="url"
              maxLength={1000}
              autoComplete="off"
              placeholder="https://api.example.com/v1"
            />
          </label>
          <SecretInput
            id="summary-api-key"
            label="API Key"
            configured={config.summary_api_key_configured}
            hint={config.summary_api_key_hint}
            value={draft.secrets.summary_api_key}
            clearChecked={draft.clearSecrets.summary_api_key}
            onChange={(value) => setSecret("summary_api_key", value)}
            onClear={(checked) => setClearSecret("summary_api_key", checked)}
          />
          <div className="summary-switches">
            <Toggle
              checked={draft.summaryEnabled}
              onChange={(checked) => changeDraft((current) => ({
                ...current,
                summaryEnabled: checked,
              }))}
              label="启用外部总结"
            />
            <Toggle
              checked={draft.summaryIncludeClinicalText}
              onChange={(checked) => changeDraft((current) => ({
                ...current,
                summaryIncludeClinicalText: checked,
              }))}
              label="发送主诉与病史"
            />
          </div>
        </div>
        <div className="integration-boundary-note">
          <ShieldCheck size={16} />
          <span>原始影像不会发送至外部总结接口。</span>
        </div>
      </section>

      <section className="panel integration-section search-config-section">
        <div className="section-heading integration-section-heading">
          <div>
            <span className="section-kicker"><Search size={14} /> 检索增强</span>
            <h2>网络搜索 API</h2>
            <span>按顺序尝试已保存且可用的服务商</span>
          </div>
          <Toggle
            checked={draft.webSearchEnabled}
            onChange={(checked) => changeDraft((current) => ({
              ...current,
              webSearchEnabled: checked,
            }))}
            label="启用搜索"
            compact
          />
        </div>

        <div className="search-control-grid">
          <label>
            最大结果数
            <input
              type="number"
              min={1}
              max={10}
              value={draft.webSearchMaxResults}
              onChange={(event) => changeDraft((current) => ({
                ...current,
                webSearchMaxResults: Math.max(1, Math.min(10, Number(event.target.value) || 1)),
              }))}
            />
          </label>
          <Toggle
            checked={draft.webSearchIncludeComplaint}
            onChange={(checked) => changeDraft((current) => ({
              ...current,
              webSearchIncludeComplaint: checked,
            }))}
            label="搜索词包含主诉"
          />
        </div>

        <div className="provider-list-heading">
          <div>
            <h3>服务商与尝试顺序</h3>
            <span>{config.search_provider_order.length} 个已保存顺序项</span>
          </div>
          <Globe2 size={19} />
        </div>

        <div className="provider-list">
          {draft.providerOrder.map((providerId, index) => {
            const provider = providers.find((item) => item.id === providerId);
            if (!provider) return null;
            const savedConfigured = isProviderConfigured(config, provider);
            return (
              <div
                className={`provider-row${draft.providerEnabled[providerId] ? "" : " excluded"}`}
                key={providerId}
              >
                <div className="provider-row-heading">
                  <div className="provider-identity">
                    <span className="provider-order">{String(index + 1).padStart(2, "0")}</span>
                    <div><strong>{provider.name}</strong><small>{provider.detail}</small></div>
                    <span className={`credential-state ${savedConfigured ? "ready" : ""}`}>
                      {savedConfigured ? "已保存" : "未配置"}
                    </span>
                  </div>
                  <div className="provider-controls">
                    <label className="provider-included">
                      <input
                        type="checkbox"
                        checked={draft.providerEnabled[providerId]}
                        onChange={(event) => changeDraft((current) => ({
                          ...current,
                          providerEnabled: {
                            ...current.providerEnabled,
                            [providerId]: event.target.checked,
                          },
                        }))}
                      />
                      <span>参与</span>
                    </label>
                    <button
                      className="icon-button"
                      type="button"
                      title="上移"
                      aria-label={`将 ${provider.name} 上移`}
                      disabled={index === 0 || saving || testing !== null}
                      onClick={() => moveProvider(index, -1)}
                    ><ArrowUp size={15} /></button>
                    <button
                      className="icon-button"
                      type="button"
                      title="下移"
                      aria-label={`将 ${provider.name} 下移`}
                      disabled={index === draft.providerOrder.length - 1 || saving || testing !== null}
                      onClick={() => moveProvider(index, 1)}
                    ><ArrowDown size={15} /></button>
                    <button
                      className="button secondary compact-button"
                      type="button"
                      onClick={() => void checkProvider(providerId)}
                      disabled={saving || testing !== null || !savedConfigured}
                    >
                      {testing === providerId ? <LoaderCircle className="spin" size={14} /> : <PlugZap size={14} />}
                      检查
                    </button>
                  </div>
                </div>

                <div className="provider-fields">
                  {provider.secret && provider.configuredField && provider.hintField && (
                    <SecretInput
                      id={`${provider.id}-api-key`}
                      label="API Key"
                      configured={Boolean(config[provider.configuredField])}
                      hint={String(config[provider.hintField] ?? "")}
                      value={draft.secrets[provider.secret]}
                      clearChecked={draft.clearSecrets[provider.secret]}
                      onChange={(value) => setSecret(provider.secret!, value)}
                      onClear={(checked) => setClearSecret(provider.secret!, checked)}
                    />
                  )}
                  {provider.id === "google_cse" && (
                    <label>
                      搜索引擎 ID
                      <input
                        value={draft.googleCseId}
                        onChange={(event) => changeDraft((current) => ({
                          ...current,
                          googleCseId: event.target.value,
                        }))}
                        maxLength={300}
                        autoComplete="off"
                        placeholder="cx"
                      />
                    </label>
                  )}
                  {provider.id === "searxng" && (
                    <label>
                      实例地址
                      <input
                        value={draft.searxngBaseUrl}
                        onChange={(event) => changeDraft((current) => ({
                          ...current,
                          searxngBaseUrl: event.target.value,
                        }))}
                        type="url"
                        maxLength={1000}
                        autoComplete="off"
                        placeholder="https://search.example.com"
                      />
                    </label>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function SecretInput({
  id,
  label,
  configured,
  hint,
  value,
  clearChecked,
  onChange,
  onClear,
}: {
  id: string;
  label: string;
  configured: boolean;
  hint: string;
  value: string;
  clearChecked: boolean;
  onChange: (value: string) => void;
  onClear: (checked: boolean) => void;
}) {
  return (
    <div className="secret-field">
      <label htmlFor={id}>{label}</label>
      <div className="secret-input-wrap">
        <KeyRound size={15} aria-hidden="true" />
        <input
          id={id}
          type="password"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={configured ? hint || "已配置" : "输入密钥"}
          autoComplete="new-password"
          maxLength={4000}
          disabled={clearChecked}
        />
      </div>
      {configured && (
        <label className="clear-secret">
          <input
            type="checkbox"
            checked={clearChecked}
            onChange={(event) => onClear(event.target.checked)}
          />
          <span>清除已保存密钥</span>
        </label>
      )}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  compact = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  compact?: boolean;
}) {
  return (
    <label className={`toggle-control${compact ? " compact" : ""}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true"><span /></span>
      <span>{label}</span>
    </label>
  );
}
