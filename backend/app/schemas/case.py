from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CaseCreate(BaseModel):
    patient_age: int = Field(ge=0, le=130)
    patient_sex: str = Field(pattern="^(F|M|U)$")
    complaint: str = Field(min_length=2, max_length=2000)
    medical_history: str = Field(default="", max_length=4000)
    affected_eye: Literal["OD", "OS", "OU", "UNKNOWN"] = "UNKNOWN"
    consent_confirmed: bool

    @model_validator(mode="after")
    def consent_is_required(self) -> "CaseCreate":
        if not self.consent_confirmed:
            raise ValueError("需确认已获得病例资料使用授权")
        return self


CaseStatus = Literal["created", "analyzing", "awaiting_review", "reviewed", "failed"]
ImageKind = Literal["fundus", "ultrawide", "oct", "anterior", "other"]
StepStatus = Literal["pending", "running", "completed", "skipped", "failed"]


class CaseImage(BaseModel):
    id: str
    filename: str
    kind: ImageKind
    content_type: str
    size_bytes: int
    url: str


class PipelineStage(BaseModel):
    key: str
    label: str
    status: StepStatus
    detail: str = ""


class Finding(BaseModel):
    label: str
    location: str = ""
    confidence: float = Field(ge=0, le=1)


class Differential(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)


class Evidence(BaseModel):
    id: str
    source: str
    snippet: str
    score: float = Field(ge=0, le=1)


class WebEvidence(BaseModel):
    title: str
    url: str
    snippet: str = ""
    provider: str
    score: float | None = Field(default=None, ge=0, le=1)


class ComponentResult(BaseModel):
    key: str
    label: str
    status: StepStatus
    detail: str = ""
    latency_ms: int = Field(default=0, ge=0)


class AnalysisResult(BaseModel):
    status: Literal["queued", "running", "completed", "failed"]
    model_mode: Literal["mock", "remote"]
    stages: list[PipelineStage] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    impression: str = ""
    differential: list[Differential] = Field(default_factory=list)
    urgency: Literal["unknown", "low", "medium", "high"] = "unknown"
    recommendations: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    web_evidence: list[WebEvidence] = Field(default_factory=list)
    component_results: list[ComponentResult] = Field(default_factory=list)
    summary: str = ""
    external_summary_used: bool = False
    external_payload: dict[str, Any] = Field(default_factory=dict)
    runtime_metadata: dict[str, Any] = Field(default_factory=dict)
    toolchain_plan: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    safety_flags: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None
    error: str = ""


ReviewDecision = Literal["accepted", "modified", "rejected"]


class ReviewUpdate(BaseModel):
    decision: ReviewDecision
    final_impression: str = Field(default="", max_length=2000)
    note: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="医生", min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_review_reason(self) -> "ReviewUpdate":
        if self.decision in {"modified", "rejected"} and len(self.note.strip()) < 2:
            raise ValueError("修改或驳回结论时需填写复核说明")
        return self


class CaseReview(ReviewUpdate):
    reviewed_at: datetime


class CaseRead(BaseModel):
    id: str
    owner_id: str = ""
    owner_name: str = ""
    patient_age: int
    patient_sex: str
    complaint: str
    medical_history: str
    affected_eye: Literal["OD", "OS", "OU", "UNKNOWN"]
    consent_confirmed: bool
    status: CaseStatus
    images: list[CaseImage] = Field(default_factory=list)
    analysis: AnalysisResult | None = None
    review: CaseReview | None = None
    created_at: datetime
    updated_at: datetime


class CaseListPage(BaseModel):
    items: list[CaseRead] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=8, ge=1)


class CaseStats(BaseModel):
    total: int = 0
    analyzing: int = 0
    awaiting_review: int = 0
    reviewed: int = 0


class ModelService(BaseModel):
    role: str
    name: str
    status: Literal["mock", "configured", "offline"]
    required: bool = True
    enabled: bool = True
    endpoint: str = ""


class SystemOverview(BaseModel):
    stats: CaseStats
    model_mode: Literal["mock", "remote"]
    models: list[ModelService]
    disclaimer: str


KnowledgeCategory = Literal["guideline", "literature", "case", "other"]


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=2, max_length=20000)
    source: str = Field(default="", max_length=1000)
    category: KnowledgeCategory = "other"
    vector: list[float] | None = None

    @model_validator(mode="after")
    def embedding_shape(self) -> "KnowledgeDocumentCreate":
        if self.vector is not None and not self.vector:
            raise ValueError("向量不能为空")
        if any(not -1e9 < value < 1e9 for value in self.vector or []):
            raise ValueError("向量包含无效数值")
        return self


class KnowledgeDocument(BaseModel):
    id: str
    title: str
    content: str
    source: str = ""
    category: KnowledgeCategory = "other"
    created_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(default="", max_length=4000)
    vector: list[float] | None = None
    top_k: int = Field(
        default_factory=lambda: _settings().vector_top_k,
        ge=1,
        le=50,
    )
    category: KnowledgeCategory | None = None

    @model_validator(mode="after")
    def query_or_vector(self) -> "KnowledgeSearchRequest":
        if not self.query.strip() and self.vector is None:
            raise ValueError("请提供检索文本或向量")
        return self


class KnowledgeMatch(BaseModel):
    document: KnowledgeDocument
    score: float = Field(ge=0, le=1)


class KnowledgeIndexStatus(BaseModel):
    backend: Literal["zvec"] = "zvec"
    collection: str
    path: str
    documents: int
    dimension: int
    embedding_mode: Literal["memory", "local", "remote"]
    model_path: str = ""
    device: str = ""
    ready: bool


def _settings():
    from app.core.config import get_settings

    return get_settings()
