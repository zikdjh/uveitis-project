from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents import SkillAvailability, ToolchainPlan, ToolchainPlanner
from app.core.config import Settings
from app.schemas.case import (
    AnalysisResult,
    CaseRead,
    ComponentResult,
    Differential,
    Evidence,
    Finding,
    ModelService,
    PipelineStage,
    WebEvidence,
)
from app.services.integrations import IntegrationResult, OptionalIntegrations


_PROTOCOL_LABELS = {
    "openai_responses": "OpenAI Responses API",
    "openai_chat_completions": "OpenAI Chat Completions API",
    "anthropic_messages": "Anthropic Messages API",
}


def _protocol_label(protocol: str | None) -> str:
    """Human-readable name for the configured external summary protocol."""

    return _PROTOCOL_LABELS.get(str(protocol or ""), "外部总结 API")


class AnalysisService:
    """Coordinates optional judgment branches without gating the core workflow."""

    def __init__(
        self,
        settings: Settings,
        knowledge_store: Any | None = None,
        integrations: OptionalIntegrations | None = None,
        planner: ToolchainPlanner | None = None,
    ) -> None:
        self.settings = settings
        self.knowledge_store = knowledge_store
        self.integrations = integrations or OptionalIntegrations(settings)
        self.planner = planner or ToolchainPlanner(
            settings,
            integrations=self.integrations,
        )

    def _configured(self, enabled: bool) -> str:
        if self.settings.model_mode != "remote" or not enabled:
            return "offline"
        return "configured"

    def model_services(self) -> list[ModelService]:
        config = self.integrations.public_config()
        return [
            ModelService(
                role="Qwen 微调判断（可选）",
                name=self.settings.perception_model,
                status=self._configured(self.integrations.qwen_available),
                required=False,
                enabled=self.settings.qwen_judgment_enabled,
                endpoint=self.settings.perception_service_url,
            ),
            ModelService(
                role="RAG 向量检索（可选）",
                name=self.settings.retrieval_model,
                status=self._configured(self._rag_available()),
                required=False,
                enabled=self.settings.rag_enabled,
                endpoint=self.settings.retrieval_service_url,
            ),
            ModelService(
                role="补充决策（可选）",
                name=self.settings.decision_model,
                status=self._configured(self.integrations.decision_available),
                required=False,
                enabled=self.settings.decision_enabled,
                endpoint=self.settings.decision_service_url,
            ),
            ModelService(
                role="网络搜索辅助（可选）",
                name="多搜索 API",
                status=self._configured(config.web_search_enabled),
                required=False,
                enabled=config.web_search_enabled,
                endpoint="管理员配置",
            ),
            ModelService(
                role="外部总结（可选）",
                name=config.summary_model or _protocol_label(config.summary_protocol),
                status=self._configured(self.integrations.summary_available),
                required=False,
                enabled=config.summary_enabled,
                endpoint="管理员配置",
            ),
        ]

    def _rag_available(self) -> bool:
        if not self.settings.rag_enabled or self.knowledge_store is None:
            return False
        try:
            return bool(
                self.knowledge_store.repository.exists()
                and self.knowledge_store.repository.count() > 0
            )
        except Exception:
            return False

    def _skill_availability(self) -> dict[str, SkillAvailability]:
        """Report which optional skills can run, and why the rest cannot."""

        config = self.integrations.public_config()
        if self.settings.model_mode != "remote":
            offline = "当前为 mock 模式，未接入外部模型服务"
            return {
                "qwen_judgment": SkillAvailability(False, offline),
                "retrieval": SkillAvailability(False, offline),
                "decision": SkillAvailability(False, offline),
                "web_search": SkillAvailability(False, offline),
                "external_summary": SkillAvailability(False, offline),
            }

        if not self.settings.qwen_judgment_enabled:
            qwen = SkillAvailability(False, "Qwen 微调判断未启用")
        elif not self.settings.perception_service_url.strip():
            qwen = SkillAvailability(False, "Qwen 微调判断服务地址未配置")
        else:
            qwen = SkillAvailability(True, "已配置")

        if not self.settings.rag_enabled:
            retrieval = SkillAvailability(False, "RAG 向量检索未启用")
        elif not self._rag_available():
            retrieval = SkillAvailability(False, "本地知识索引为空或尚未就绪")
        else:
            retrieval = SkillAvailability(True, "已配置且知识索引可用")

        if not self.settings.decision_enabled:
            decision = SkillAvailability(
                False,
                "补充决策模型训练暂缓，槽位保留但未启用",
            )
        elif not self.settings.decision_service_url.strip():
            decision = SkillAvailability(False, "补充决策服务地址未配置")
        else:
            decision = SkillAvailability(True, "已配置")

        if not config.web_search_enabled:
            web_search = SkillAvailability(False, "网络搜索 API 未启用")
        else:
            web_search = SkillAvailability(True, "管理员已启用网络搜索")

        if not config.summary_enabled:
            summary = SkillAvailability(False, "外部总结 API 未启用")
        elif not self.integrations.summary_available:
            summary = SkillAvailability(False, "外部总结凭据不完整")
        else:
            summary = SkillAvailability(True, "已配置")

        return {
            "qwen_judgment": qwen,
            "retrieval": retrieval,
            "decision": decision,
            "web_search": web_search,
            "external_summary": summary,
        }

    @staticmethod
    def _stages() -> list[PipelineStage]:
        return [
            PipelineStage(key="intake", label="病例结构化", status="completed"),
            PipelineStage(
                key="planning",
                label="工具链规划",
                status="pending",
            ),
            PipelineStage(key="preprocess", label="影像预处理", status="pending"),
            PipelineStage(
                key="qwen_judgment",
                label="Qwen 微调判断",
                status="pending",
            ),
            PipelineStage(key="retrieval", label="RAG 证据检索", status="pending"),
            PipelineStage(key="decision", label="补充决策", status="pending"),
            PipelineStage(key="web_search", label="网络搜索辅助", status="pending"),
            PipelineStage(
                key="external_summary",
                label="外部 API 总结",
                status="pending",
            ),
            PipelineStage(key="safety", label="安全校验", status="pending"),
            PipelineStage(key="report", label="报告整理", status="pending"),
        ]

    @staticmethod
    def _component_result(
        key: str,
        label: str,
        result: IntegrationResult,
    ) -> ComponentResult:
        return ComponentResult(
            key=key,
            label=label,
            status=result.status,
            detail=result.detail,
            latency_ms=result.latency_ms,
        )

    @staticmethod
    def _plan_skip(
        plan: ToolchainPlan,
        key: str,
        default: str,
    ) -> IntegrationResult:
        reason = plan.skipped.get(key)
        if not reason:
            return IntegrationResult("skipped", default)
        return IntegrationResult("skipped", f"工具链规划跳过：{reason}")

    @staticmethod
    def _plan_detail(plan: ToolchainPlan) -> str:
        planner_label = (
            "AgentScope 模型规划"
            if plan.planner == "agentscope"
            else "确定性兜底规划"
        )
        executed = "、".join(plan.steps) if plan.steps else "无"
        detail = f"{planner_label}：本次执行 {executed}"
        if plan.skipped:
            detail += f"；跳过 {len(plan.skipped)} 项"
        if plan.rationale:
            detail += f"。{plan.rationale}"
        if plan.notes:
            detail += "（" + "；".join(plan.notes) + "）"
        return detail

    @staticmethod
    def _set_stage(
        stages: list[PipelineStage],
        key: str,
        result: IntegrationResult,
    ) -> None:
        stage = next(item for item in stages if item.key == key)
        stage.status = result.status
        stage.detail = result.detail

    def start(self) -> AnalysisResult:
        return AnalysisResult(
            status="queued",
            model_mode=self.settings.model_mode,
            stages=self._stages(),
            summary="分析任务已排队，增强模块将按可用性逐个执行。",
            started_at=datetime.now(UTC),
        )

    def _retrieve(self, query: str) -> IntegrationResult:
        if not self.settings.rag_enabled:
            return IntegrationResult("skipped", "RAG 向量检索未启用")
        if self.knowledge_store is None or not self._rag_available():
            return IntegrationResult("skipped", "本地知识索引为空或尚未就绪")
        started = datetime.now(UTC)
        try:
            matches = self.knowledge_store.search(
                query=query,
                vector=None,
                top_k=self.settings.vector_top_k,
            )
            evidence = [
                Evidence(
                    id=match.document.id,
                    source=match.document.source or match.document.title,
                    snippet=match.document.content,
                    score=match.score,
                )
                for match in matches
            ]
            if not evidence:
                return IntegrationResult("skipped", "RAG 检索未返回证据")
            latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            return IntegrationResult(
                "completed",
                f"RAG 返回 {len(evidence)} 条证据",
                {"evidence": evidence},
                latency_ms,
            )
        except Exception as exc:
            latency_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            return IntegrationResult(
                "failed",
                f"RAG 检索不可用: {type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )

    @staticmethod
    def _deterministic_summary(
        judgment: dict[str, Any],
        decision: dict[str, Any],
        evidence: list[Evidence],
        web_evidence: list[WebEvidence],
    ) -> str:
        parts: list[str] = []
        label = judgment.get("label") or judgment.get("impression")
        if label:
            parts.append(f"Qwen 判断：{label}")
        primary = decision.get("primary_class")
        if primary:
            parts.append(f"补充决策：{primary}")
        if evidence:
            parts.append(f"RAG 证据 {len(evidence)} 条")
        if web_evidence:
            parts.append(f"网络辅助结果 {len(web_evidence)} 条")
        if not parts:
            parts.append("当前未获得可复核的模型证据")
        return "；".join(parts) + "。该内容仅作辅助参考，必须由医生结合原始资料复核。"

    def analyze(self, case: CaseRead, queued: AnalysisResult) -> AnalysisResult:
        stages = self._stages()
        components: list[ComponentResult] = []
        for stage in stages:
            if stage.key == "intake":
                stage.status = "completed"
            elif stage.key == "preprocess":
                stage.status = "completed" if case.images else "skipped"
                stage.detail = (
                    f"已接收 {len(case.images)} 张影像" if case.images else "无影像，仅走文本路径"
                )

        availability = self._skill_availability()
        plan = self.planner.plan(case=case, availability=availability)
        planning_stage = next(item for item in stages if item.key == "planning")
        planning_stage.status = "completed"
        planning_stage.detail = self._plan_detail(plan)

        judgment_result = (
            self.integrations.qwen_judgment(case)
            if "qwen_judgment" in plan.steps
            else self._plan_skip(plan, "qwen_judgment", "Qwen 微调判断未执行")
        )
        self._set_stage(stages, "qwen_judgment", judgment_result)
        components.append(
            self._component_result("qwen_judgment", "Qwen 微调判断", judgment_result)
        )
        judgment = judgment_result.data if judgment_result.status == "completed" else {}

        query_parts = [case.complaint]
        query_parts.extend(
            str(item.get("label", ""))
            for item in judgment.get("findings", [])
            if isinstance(item, dict)
        )
        if judgment.get("label"):
            query_parts.append(str(judgment["label"]))
        retrieval_result = (
            self._retrieve(" ".join(query_parts).strip() or "葡萄膜炎")
            if "retrieval" in plan.steps
            else self._plan_skip(plan, "retrieval", "RAG 向量检索未执行")
        )
        self._set_stage(stages, "retrieval", retrieval_result)
        components.append(
            self._component_result("retrieval", "RAG 证据检索", retrieval_result)
        )
        evidence = (
            retrieval_result.data.get("evidence", [])
            if retrieval_result.status == "completed"
            else []
        )

        decision_result = (
            self.integrations.decision(case, judgment, evidence)
            if "decision" in plan.steps
            else self._plan_skip(plan, "decision", "补充决策模型未执行")
        )
        self._set_stage(stages, "decision", decision_result)
        components.append(
            self._component_result("decision", "补充决策", decision_result)
        )
        decision = decision_result.data if decision_result.status == "completed" else {}

        search_result = (
            self.integrations.web_search(case, judgment, decision)
            if "web_search" in plan.steps
            else self._plan_skip(plan, "web_search", "网络搜索未执行")
        )
        self._set_stage(stages, "web_search", search_result)
        components.append(
            self._component_result("web_search", "网络搜索辅助", search_result)
        )
        web_evidence = (
            search_result.data.get("results", [])
            if search_result.status == "completed"
            else []
        )

        summary_result = (
            self.integrations.external_summary(
                case,
                judgment,
                decision,
                evidence,
                web_evidence,
            )
            if "external_summary" in plan.steps
            else self._plan_skip(plan, "external_summary", "外部总结未执行")
        )
        self._set_stage(stages, "external_summary", summary_result)
        components.append(
            self._component_result("external_summary", "外部 API 总结", summary_result)
        )

        summary = (
            str(summary_result.data.get("summary") or "").strip()
            if summary_result.status == "completed"
            else self._deterministic_summary(judgment, decision, evidence, web_evidence)
        )
        recommendations: list[str] = []
        for source in (
            judgment.get("recommendations", []),
            decision.get("recommendations", []),
            summary_result.data.get("recommendations", []),
        ):
            for item in source if isinstance(source, list) else []:
                text = str(item).strip()
                if text and text not in recommendations:
                    recommendations.append(text)

        findings = [
            Finding(
                label=str(item.get("label") or "未命名发现"),
                location=str(item.get("location") or ""),
                confidence=float(item.get("confidence") or 0),
            )
            for item in judgment.get("findings", [])
            if isinstance(item, dict)
        ]
        differential = [
            Differential(
                label=str(item.get("label") or "未命名判断"),
                confidence=float(item.get("confidence") or 0),
            )
            for item in decision.get("differential", [])
            if isinstance(item, dict)
        ]

        impression = (
            str(judgment.get("impression") or "").strip()
            or str(decision.get("primary_class") or "").strip()
            or "本次未形成可复核的临床结论，请结合检查资料进行判断。"
        )
        confidence = max(
            float(judgment.get("confidence") or 0),
            float(decision.get("confidence") or 0),
        )
        urgency = str(decision.get("urgency") or "unknown")
        if urgency not in {"low", "medium", "high", "unknown"}:
            urgency = "unknown"

        safety_flags = ["辅助结果，必须由医生复核"]
        if plan.planner != "agentscope":
            safety_flags.append("工具链由确定性规则编排，未使用模型规划")
        if judgment_result.status == "failed":
            safety_flags.append("Qwen 微调判断不可用，已跳过")
        if retrieval_result.status == "skipped":
            safety_flags.append("RAG 未返回可用证据")
        if summary_result.status != "completed":
            safety_flags.append("外部总结未使用")

        safety_stage = next(item for item in stages if item.key == "safety")
        safety_stage.status = "completed"
        safety_stage.detail = "增强模块失败或不可用时已跳过，未阻断医生复核链路"
        report_stage = next(item for item in stages if item.key == "report")
        report_stage.status = "completed"
        report_stage.detail = (
            "已使用外部 API 总结"
            if summary_result.status == "completed"
            else "已生成确定性回退摘要"
        )

        return AnalysisResult(
            status="completed",
            model_mode=queued.model_mode,
            stages=stages,
            findings=findings,
            impression=impression,
            differential=differential,
            urgency=urgency,
            recommendations=recommendations,
            evidence=evidence,
            web_evidence=web_evidence,
            component_results=components,
            summary=summary,
            external_summary_used=summary_result.status == "completed",
            external_payload=(
                summary_result.data if summary_result.status == "completed" else {}
            ),
            runtime_metadata=(
                judgment.get("runtime", {})
                if judgment_result.status == "completed"
                else {}
            ),
            toolchain_plan=plan.as_dict(),
            confidence=confidence,
            safety_flags=safety_flags,
            started_at=queued.started_at,
            completed_at=datetime.now(UTC),
        )
