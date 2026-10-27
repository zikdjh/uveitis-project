import {
  ApiOutlined,
  KeyOutlined,
  ReloadOutlined,
  SaveOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  ConfigProvider,
  Form,
  Input,
  InputNumber,
  Pagination,
  Row,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";

import {
  getIntegrationConfig,
  testIntegration,
  testSearchProviders,
  updateIntegrationConfig,
  type IntegrationConfig,
  type IntegrationTestBatchResult,
  type IntegrationUpdate,
  type SearchProvider,
  type SummaryProtocol,
} from "@/api/integrations";

const { Text, Title } = Typography;
const PROVIDERS_PER_PAGE = 4;
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
  { id: "searxng", name: "SearXNG", detail: "自建元搜索" },
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

type Draft = {
  summaryEnabled: boolean;
  summaryProtocol: SummaryProtocol;
  summaryBaseUrl: string;
  summaryModel: string;
  webSearchEnabled: boolean;
  webSearchMaxResults: number;
  googleCseId: string;
  searxngBaseUrl: string;
  secrets: Record<SecretField, string>;
  providerOrder: SearchProvider[];
  providerEnabled: Record<SearchProvider, boolean>;
};

const protocolLabels: Record<SummaryProtocol, string> = {
  openai_responses: "OpenAI Responses",
  openai_chat_completions: "OpenAI Chat Completions",
  anthropic_messages: "Anthropic Messages",
};

function completeProviderOrder(order: SearchProvider[]) {
  const unique = [...new Set(order)].filter((item) => providerOrderSeed.includes(item));
  return [...unique, ...providerOrderSeed.filter((item) => !unique.includes(item))];
}

function emptySecretDraft() {
  return Object.fromEntries(secretFields.map((field) => [field, ""])) as Record<SecretField, string>;
}

function draftFromConfig(config: IntegrationConfig): Draft {
  const providerOrder = completeProviderOrder(config.search_provider_order);
  const providerEnabled = Object.fromEntries(
    providerOrderSeed.map((provider) => [provider, false]),
  ) as Record<SearchProvider, boolean>;
  for (const provider of providerOrder) providerEnabled[provider] = true;
  return {
    summaryEnabled: config.summary_enabled,
    summaryProtocol: config.summary_protocol,
    summaryBaseUrl: config.summary_base_url,
    summaryModel: config.summary_model,
    webSearchEnabled: config.web_search_enabled,
    webSearchMaxResults: config.web_search_max_results,
    googleCseId: config.google_cse_id,
    searxngBaseUrl: config.searxng_base_url,
    secrets: emptySecretDraft(),
    providerOrder,
    providerEnabled,
  };
}

function buildUpdate(draft: Draft, revision: number) {
  const payload: IntegrationUpdate = {
    summary_enabled: draft.summaryEnabled,
    summary_protocol: draft.summaryProtocol,
    summary_base_url: draft.summaryBaseUrl.trim(),
    summary_model: draft.summaryModel.trim(),
    web_search_enabled: draft.webSearchEnabled,
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
  }
  return payload;
}

function isProviderConfigured(config: IntegrationConfig, provider: ProviderDescriptor) {
  if (provider.id === "searxng") return Boolean(config.searxng_base_url.trim());
  const configured = provider.configuredField ? Boolean(config[provider.configuredField]) : false;
  if (provider.id === "google_cse") return configured && Boolean(config.google_cse_id.trim());
  return configured;
}

export default function AntdServicesPage() {
  const [config, setConfig] = useState<IntegrationConfig | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [searchChecks, setSearchChecks] = useState<IntegrationTestBatchResult | null>(null);
  const [providerPage, setProviderPage] = useState(1);
  const [credentialEditor, setCredentialEditor] = useState<SearchProvider | null>(null);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();

  const configuredProviders = useMemo(
    () => config ? providers.filter((provider) => isProviderConfigured(config, provider)).length : 0,
    [config],
  );

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const loaded = await getIntegrationConfig();
      setConfig(loaded);
      setDraft(draftFromConfig(loaded));
      setDirty(false);
      setSearchChecks(null);
      setProviderPage(1);
      setCredentialEditor(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "服务配置加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!draft) return;
    const pageCount = Math.ceil(draft.providerOrder.length / PROVIDERS_PER_PAGE);
    setProviderPage((current) => Math.min(current, Math.max(pageCount, 1)));
  }, [draft]);

  function changeDraft(updater: (current: Draft) => Draft) {
    setDraft((current) => current ? updater(current) : current);
    setDirty(true);
  }

  function setSecret(field: SecretField, value: string) {
    changeDraft((current) => ({
      ...current,
      secrets: { ...current.secrets, [field]: value },
    }));
  }

  function moveProvider(index: number, direction: -1 | 1) {
    changeDraft((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.providerOrder.length) return current;
      const providerOrder = [...current.providerOrder];
      [providerOrder[index], providerOrder[target]] = [providerOrder[target], providerOrder[index]];
      return { ...current, providerOrder };
    });
  }

  async function persistDraft(showSuccess = true) {
    if (!draft || !config) return null;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateIntegrationConfig(buildUpdate(draft, config.revision));
      setConfig(updated);
      setDraft(draftFromConfig(updated));
      setDirty(false);
      if (showSuccess) void messageApi.success(`配置已保存，版本 ${updated.revision}。`);
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
    try {
      const result = await testIntegration({ kind: "summary" });
      if (!result.ok) throw new Error(result.detail);
      void messageApi.success(`${result.detail}，耗时 ${result.latency_ms} ms。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "外部总结检查失败");
    } finally {
      setTesting(null);
    }
  }

  async function checkSearchProviders() {
    const savedConfig = dirty ? await persistDraft(false) : config;
    if (!savedConfig) return;
    const savedProviders = savedConfig.search_provider_order.filter((providerId) => {
      const provider = providers.find((item) => item.id === providerId);
      return provider ? isProviderConfigured(savedConfig, provider) : false;
    });
    if (!savedProviders.length) {
      setSearchChecks(null);
      setError("没有已配置连接凭据的搜索服务商");
      return;
    }
    setTesting("search-all");
    setError(null);
    try {
      const result = await testSearchProviders({ providers: savedProviders, query: "uveitis clinical guideline" });
      setSearchChecks(result);
      if (result.succeeded > 0) {
        void messageApi.success(`搜索 API 检查完成：${result.succeeded} 家可用，${result.failed} 家不可用。`);
      } else {
        setError("搜索 API 检查完成，但没有服务商可用；请先配置至少一个服务商的凭据。");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "搜索 API 检查失败");
    } finally {
      setTesting(null);
    }
  }

  async function checkProvider(provider: SearchProvider) {
    if (dirty && !(await persistDraft(false))) return;
    setTesting(provider);
    setError(null);
    try {
      const result = await testIntegration({ kind: "search", provider, query: "uveitis clinical guideline" });
      if (!result.ok) throw new Error(result.detail);
      void messageApi.success(`${result.detail}，耗时 ${result.latency_ms} ms。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "搜索服务检查失败");
    } finally {
      setTesting(null);
    }
  }

  if (loading && !config) {
    return (
      <section className="page antd-services-page antd-services-loading">
        <Spin size="large" tip="正在读取服务配置"><div className="antd-services-loading-box" /></Spin>
      </section>
    );
  }

  if (!config || !draft) {
    return (
      <section className="page antd-services-page">
        <Card><Alert type="error" showIcon message={error ?? "服务配置不可用"} action={<Button icon={<ReloadOutlined />} onClick={() => void load()}>重新读取</Button>} /></Card>
      </section>
    );
  }

  const visibleProviderIds = draft.providerOrder.slice((providerPage - 1) * PROVIDERS_PER_PAGE, providerPage * PROVIDERS_PER_PAGE);
  const busy = saving || testing !== null;

  return (
    <ConfigProvider theme={{ components: { Card: { bodyPadding: 0 } } }}>
      {contextHolder}
      <section className="page antd-services-page">
        <div className="antd-services-titlebar">
          <div>
            <Title level={2}>服务配置</Title>
            {dirty && <Tag color="gold">修改尚未保存</Tag>}
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} loading={loading} disabled={saving || testing !== null} onClick={() => void load()}>
              重新读取
            </Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} disabled={testing !== null || !dirty} onClick={() => void persistDraft()}>
              {dirty ? "保存配置" : "配置已保存"}
            </Button>
          </Space>
        </div>

        {error && (
          <Alert
            className="antd-services-alert"
            type="error"
            showIcon
            closable
            message={error}
            onClose={() => setError(null)}
          />
        )}

        <Card
          id="summary-api"
          className="antd-service-card"
          title={<span className="antd-service-heading"><ApiOutlined /> 总结 API</span>}
          extra={
            <Space wrap>
              <Tag>{protocolLabels[draft.summaryProtocol]}</Tag>
              <Button size="small" loading={testing === "summary"} disabled={busy} onClick={() => void checkSummary()}>
                检查连接
              </Button>
            </Space>
          }
        >
          <div className="antd-service-section">
            <Text strong>连接参数</Text>
            <Form layout="vertical" requiredMark={false}>
              <Form.Item label="API 地址">
                <Input
                  value={draft.summaryBaseUrl}
                  onChange={(event) => changeDraft((current) => ({
                    ...current,
                    summaryBaseUrl: event.target.value,
                  }))}
                  maxLength={1000}
                  placeholder="https://api.example.com/v1"
                />
              </Form.Item>
              <Row gutter={[16, 0]}>
                <Col xs={24} md={12}>
                  <Form.Item label="接口协议">
                    <Select
                      value={draft.summaryProtocol}
                      options={(Object.keys(protocolLabels) as SummaryProtocol[]).map((protocol) => ({
                        value: protocol,
                        label: protocolLabels[protocol],
                      }))}
                      onChange={(value: SummaryProtocol) => changeDraft((current) => ({
                        ...current,
                        summaryProtocol: value,
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item label="模型名称">
                    <Input
                      value={draft.summaryModel}
                      onChange={(event) => changeDraft((current) => ({
                        ...current,
                        summaryModel: event.target.value,
                      }))}
                      maxLength={200}
                      placeholder="model-id"
                    />
                  </Form.Item>
                </Col>
              </Row>
            </Form>
          </div>
          <div className="antd-service-section">
            <Form layout="vertical" requiredMark={false}>
              <Form.Item label="API Key" className="antd-secret-field">
                <Input.Password
                  prefix={<KeyOutlined />}
                  value={draft.secrets.summary_api_key}
                  onChange={(event) => setSecret("summary_api_key", event.target.value)}
                  placeholder={config.summary_api_key_configured ? config.summary_api_key_hint || "已配置" : "输入密钥"}
                  autoComplete="new-password"
                  maxLength={4000}
                />
              </Form.Item>
            </Form>
            <Space wrap size={10}>
              <Switch
                checked={draft.summaryEnabled}
                onChange={(checked) => changeDraft((current) => ({ ...current, summaryEnabled: checked }))}
                checkedChildren="启用"
                unCheckedChildren="停用"
              />
              <Text>启用外部总结</Text>
              <Text type="secondary">仅发送模型标签、置信度和检索证据；病例与影像不会外发</Text>
            </Space>
          </div>
        </Card>

        <Card
          id="search-api"
          className="antd-service-card"
          title={<span className="antd-service-heading"><SearchOutlined /> 网络搜索 API</span>}
          extra={
            <Space wrap>
              <Button
                size="small"
                loading={testing === "search-all"}
                disabled={busy || configuredProviders === 0}
                title={configuredProviders === 0 ? "请先配置至少一个搜索服务商" : undefined}
                onClick={() => void checkSearchProviders()}
              >
                测试全部
              </Button>
              <Switch
                checked={draft.webSearchEnabled}
                onChange={(checked) => changeDraft((current) => ({ ...current, webSearchEnabled: checked }))}
                checkedChildren="启用"
                unCheckedChildren="关闭"
              />
            </Space>
          }
        >
          <div className="antd-service-section">
            <Text strong>检索参数</Text>
            <Form layout="vertical" requiredMark={false}>
              <Form.Item label="最大结果数">
                <InputNumber
                  className="antd-max-results"
                  min={1}
                  max={10}
                  value={draft.webSearchMaxResults}
                  onChange={(value) => changeDraft((current) => ({
                    ...current,
                    webSearchMaxResults: value ?? 1,
                  }))}
                />
              </Form.Item>
            </Form>
          </div>

          <div className="antd-service-section">
            <Text type="secondary">搜索词仅使用模型标签，不包含病例、影像或未受控文本</Text>
          </div>

          {searchChecks && (
            <div className="antd-service-section">
              <div className="antd-test-summary">
                <Text strong>连通性测试结果</Text>
                <Text type="secondary">{searchChecks.succeeded} 家成功 · {searchChecks.failed} 家失败</Text>
                <Button type="link" size="small" onClick={() => setSearchChecks(null)}>收起</Button>
              </div>
              <Space direction="vertical" size={6} className="antd-test-results">
                {searchChecks.items.map((item, index) => (
                  <Alert
                    key={item.provider ?? index}
                    showIcon
                    type={item.ok ? "success" : "error"}
                    message={providers.find((provider) => provider.id === item.provider)?.name ?? item.provider}
                    description={`${item.detail} · ${item.latency_ms} ms`}
                  />
                ))}
              </Space>
            </div>
          )}

          <div className="antd-provider-heading">
            <Text strong>服务商与尝试顺序</Text>
            <Text type="secondary">按顺序尝试，不可用时跳过</Text>
          </div>

          <div className="antd-provider-list">
            {visibleProviderIds.map((providerId) => {
              const provider = providers.find((item) => item.id === providerId);
              if (!provider) return null;
              const index = draft.providerOrder.indexOf(providerId);
              const savedConfigured = isProviderConfigured(config, provider);
              const participating = draft.providerEnabled[providerId];
              const credentialOpen = credentialEditor === providerId;
              return (
                <Card
                  className={`antd-provider-card${participating ? "" : " inactive"}`}
                  size="small"
                  key={providerId}
                >
                  <div className="antd-provider-row">
                    <div className="antd-provider-meta">
                      <span className="antd-provider-index">{String(index + 1).padStart(2, "0")}</span>
                      <Space size={7} wrap>
                        <Text strong>{provider.name}</Text>
                        <Text type="secondary" className="antd-provider-detail">{provider.detail}</Text>
                        <Tag color={savedConfigured ? "green" : "default"}>{savedConfigured ? "已配置" : "未配置"}</Tag>
                      </Space>
                    </div>
                    <Space size={6} wrap>
                      <Space size={6}>
                        <Switch
                          size="small"
                          checked={participating}
                          onChange={(checked) => changeDraft((current) => ({
                            ...current,
                            providerEnabled: { ...current.providerEnabled, [providerId]: checked },
                          }))}
                        />
                        <Text>参与</Text>
                      </Space>
                      <Button
                        size="small"
                        disabled={index === 0 || busy}
                        aria-label={`${provider.name} 上移`}
                        onClick={() => moveProvider(index, -1)}
                      >
                        上移
                      </Button>
                      <Button
                        size="small"
                        disabled={index === draft.providerOrder.length - 1 || busy}
                        aria-label={`${provider.name} 下移`}
                        onClick={() => moveProvider(index, 1)}
                      >
                        下移
                      </Button>
                      <Tooltip title={credentialOpen ? "收起连接凭据" : "配置连接凭据"}>
                        <Button
                          size="small"
                          type={credentialOpen ? "primary" : "default"}
                          icon={<KeyOutlined />}
                          aria-label={`${credentialOpen ? "收起" : "配置"} ${provider.name} 连接凭据`}
                          aria-expanded={credentialOpen}
                          onClick={() => setCredentialEditor((current) =>
                            current === providerId ? null : providerId
                          )}
                        />
                      </Tooltip>
                      <Button
                        size="small"
                        loading={testing === providerId}
                        disabled={busy || !savedConfigured}
                        onClick={() => void checkProvider(providerId)}
                      >
                        检查
                      </Button>
                    </Space>
                  </div>

                  {credentialOpen && (
                    <Form layout="vertical" requiredMark={false} className="antd-provider-form">
                      {provider.secret && provider.configuredField && provider.hintField && (
                        <Form.Item label="API Key">
                          <Input.Password
                            id={`${provider.id}-api-key`}
                            prefix={<KeyOutlined />}
                            value={draft.secrets[provider.secret]}
                            onChange={(event) => setSecret(provider.secret!, event.target.value)}
                            placeholder={
                              Boolean(config[provider.configuredField])
                                ? String(config[provider.hintField] ?? "") || "已配置"
                                : "输入密钥"
                            }
                            autoComplete="new-password"
                            maxLength={4000}
                          />
                        </Form.Item>
                      )}
                      {provider.id === "google_cse" && (
                        <Form.Item label="搜索引擎 ID">
                          <Input
                            value={draft.googleCseId}
                            onChange={(event) => changeDraft((current) => ({
                              ...current,
                              googleCseId: event.target.value,
                            }))}
                            maxLength={300}
                            placeholder="cx"
                          />
                        </Form.Item>
                      )}
                      {provider.id === "searxng" && (
                        <Form.Item label="实例地址">
                          <Input
                            value={draft.searxngBaseUrl}
                            onChange={(event) => changeDraft((current) => ({
                              ...current,
                              searxngBaseUrl: event.target.value,
                            }))}
                            maxLength={1000}
                            placeholder="https://search.example.com"
                          />
                        </Form.Item>
                      )}
                    </Form>
                  )}
                </Card>
              );
            })}
          </div>

          <div className="antd-provider-pagination">
            <Pagination
              current={providerPage}
              pageSize={PROVIDERS_PER_PAGE}
              total={draft.providerOrder.length}
              showSizeChanger={false}
              showTotal={(total) => `共 ${total} 家`}
              onChange={setProviderPage}
            />
          </div>
        </Card>
      </section>
    </ConfigProvider>
  );
}
