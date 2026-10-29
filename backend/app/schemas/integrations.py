from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SummaryProtocol = Literal[
    "openai_responses",
    "openai_chat_completions",
    "anthropic_messages",
]
SearchProvider = Literal[
    "tavily",
    "brave",
    "serper",
    "searxng",
    "google_cse",
    "bing",
    "exa",
    "perplexity",
]

SECRET_KEYS = frozenset(
    {
        "summary_api_key",
        "planner_api_key",
        "tavily_api_key",
        "brave_search_api_key",
        "serper_api_key",
        "google_cse_api_key",
        "bing_search_api_key",
        "exa_api_key",
        "perplexity_api_key",
    }
)


class IntegrationConfigRead(BaseModel):
    summary_enabled: bool = False
    summary_protocol: SummaryProtocol = "openai_chat_completions"
    summary_base_url: str = ""
    summary_model: str = ""
    summary_api_key_configured: bool = False
    summary_api_key_hint: str = ""
    planner_protocol: SummaryProtocol = "openai_chat_completions"
    planner_base_url: str = ""
    planner_model: str = ""
    planner_api_key_configured: bool = False
    planner_api_key_hint: str = ""
    web_search_enabled: bool = False
    web_search_max_results: int = Field(default=5, ge=1, le=10)
    search_provider_order: list[SearchProvider] = Field(
        default_factory=lambda: [
            "tavily",
            "brave",
            "serper",
            "google_cse",
            "bing",
            "exa",
            "perplexity",
            "searxng",
        ]
    )
    tavily_api_key_configured: bool = False
    tavily_api_key_hint: str = ""
    brave_search_api_key_configured: bool = False
    brave_search_api_key_hint: str = ""
    serper_api_key_configured: bool = False
    serper_api_key_hint: str = ""
    google_cse_api_key_configured: bool = False
    google_cse_api_key_hint: str = ""
    google_cse_id: str = ""
    bing_search_api_key_configured: bool = False
    bing_search_api_key_hint: str = ""
    exa_api_key_configured: bool = False
    exa_api_key_hint: str = ""
    perplexity_api_key_configured: bool = False
    perplexity_api_key_hint: str = ""
    searxng_base_url: str = ""
    revision: int = 0
    updated_at: datetime | None = None
    updated_by: str = ""


class IntegrationConfigUpdate(BaseModel):
    summary_enabled: bool | None = None
    summary_protocol: SummaryProtocol | None = None
    summary_base_url: str | None = Field(default=None, max_length=1000)
    summary_model: str | None = Field(default=None, max_length=200)
    summary_api_key: str | None = Field(default=None, max_length=4000)
    clear_summary_api_key: bool = False
    planner_protocol: SummaryProtocol | None = None
    planner_base_url: str | None = Field(default=None, max_length=1000)
    planner_model: str | None = Field(default=None, max_length=200)
    planner_api_key: str | None = Field(default=None, max_length=4000)
    clear_planner_api_key: bool = False
    web_search_enabled: bool | None = None
    web_search_max_results: int | None = Field(default=None, ge=1, le=10)
    search_provider_order: list[SearchProvider] | None = None
    tavily_api_key: str | None = Field(default=None, max_length=4000)
    clear_tavily_api_key: bool = False
    brave_search_api_key: str | None = Field(default=None, max_length=4000)
    clear_brave_search_api_key: bool = False
    serper_api_key: str | None = Field(default=None, max_length=4000)
    clear_serper_api_key: bool = False
    google_cse_api_key: str | None = Field(default=None, max_length=4000)
    clear_google_cse_api_key: bool = False
    google_cse_id: str | None = Field(default=None, max_length=300)
    bing_search_api_key: str | None = Field(default=None, max_length=4000)
    clear_bing_search_api_key: bool = False
    exa_api_key: str | None = Field(default=None, max_length=4000)
    clear_exa_api_key: bool = False
    perplexity_api_key: str | None = Field(default=None, max_length=4000)
    clear_perplexity_api_key: bool = False
    searxng_base_url: str | None = Field(default=None, max_length=1000)
    expected_revision: int | None = None

    @model_validator(mode="after")
    def provider_order_is_unique(self) -> "IntegrationConfigUpdate":
        if self.search_provider_order is not None:
            if len(set(self.search_provider_order)) != len(self.search_provider_order):
                raise ValueError("搜索服务商顺序不能重复")
        return self


class IntegrationConfigTestRequest(BaseModel):
    kind: Literal["summary", "planner", "search"]
    provider: SearchProvider | None = None
    query: str = Field(default="uveitis clinical guideline", max_length=500)


class IntegrationConfigTestResult(BaseModel):
    ok: bool
    detail: str
    latency_ms: int = Field(default=0, ge=0)
    provider: str | None = None
    attempts: int = Field(default=0, ge=0)


class IntegrationConfigTestBatchRequest(BaseModel):
    providers: list[SearchProvider] = Field(default_factory=list, max_length=20)
    query: str = Field(default="uveitis clinical guideline", max_length=500)

    @model_validator(mode="after")
    def providers_are_unique(self) -> "IntegrationConfigTestBatchRequest":
        if len(set(self.providers)) != len(self.providers):
            raise ValueError("测试服务商不能重复")
        return self


class IntegrationConfigTestBatchResult(BaseModel):
    ok: bool
    succeeded: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    items: list[IntegrationConfigTestResult]
