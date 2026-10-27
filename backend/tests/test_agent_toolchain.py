from datetime import UTC, datetime

import httpx

from app.agents.planner import ToolchainPlanner
from app.agents.toolchain import (
    SkillAvailability,
    normalize_steps,
    skill_catalog,
)
from app.core.config import Settings
from app.schemas.case import CaseRead
from app.services.analysis import AnalysisService
from app.core.external_boundary import find_external_violations
from app.services.integrations import OptionalIntegrations


def make_case() -> CaseRead:
    now = datetime.now(UTC)
    return CaseRead(
        id="case-1",
        patient_age=42,
        patient_sex="F",
        complaint="左眼视物模糊三天",
        medical_history="无特殊",
        affected_eye="OS",
        consent_confirmed=True,
        status="created",
        created_at=now,
        updated_at=now,
    )


def availability(**overrides: bool) -> dict[str, SkillAvailability]:
    state = {
        "qwen_judgment": True,
        "retrieval": True,
        "decision": False,
        "web_search": True,
        "external_summary": True,
    }
    state.update(overrides)
    reasons = {
        "decision": "补充决策模型训练暂缓，槽位保留但未启用",
        "retrieval": "RAG 向量检索未启用",
        "web_search": "网络搜索 API 未启用",
        "external_summary": "外部总结 API 未启用",
    }
    return {
        key: SkillAvailability(value, reasons.get(key, "已配置"))
        for key, value in state.items()
    }


def test_normalize_steps_orders_drops_unknown_and_restores_core() -> None:
    plan = normalize_steps(
        ["external_summary", "not-a-skill", "qwen_judgment"],
        availability(),
        planner="agentscope",
    )

    assert plan.steps == ["qwen_judgment", "external_summary"]
    assert "未登记的工具" in plan.notes[0]
    assert "not-a-skill" not in plan.steps


def test_normalize_steps_marks_deferred_decision_slot_as_skipped() -> None:
    plan = normalize_steps(
        ["qwen_judgment", "retrieval", "decision"],
        availability(),
        planner="agentscope",
    )

    assert "decision" not in plan.steps
    assert "训练暂缓" in plan.skipped["decision"]


def test_normalize_steps_reports_unselected_optional_skill() -> None:
    plan = normalize_steps(
        ["qwen_judgment"],
        availability(),
        planner="agentscope",
    )

    assert plan.steps == ["qwen_judgment"]
    assert plan.skipped["retrieval"] == "规划器本次未选择，非必需步骤"


def test_skill_catalog_exposes_deferred_flag() -> None:
    catalog = {item["key"]: item for item in skill_catalog(availability())}

    assert catalog["decision"]["deferred"] is True
    assert catalog["decision"]["available"] is False
    assert catalog["qwen_judgment"]["available"] is True


def test_planner_falls_back_when_orchestration_disabled() -> None:
    settings = Settings(agent_orchestration_enabled=False)
    planner = ToolchainPlanner(settings)

    plan = planner.plan(case=make_case(), availability=availability())

    assert plan.planner == "heuristic"
    assert plan.steps == [
        "qwen_judgment",
        "retrieval",
        "web_search",
        "external_summary",
    ]
    assert any("未启用" in note for note in plan.notes)


def test_planner_falls_back_when_agentscope_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner.agentscope_available", lambda: False)
    settings = Settings(
        agent_orchestration_enabled=True,
        agent_planner_api_key="plan-key",
        agent_planner_model="plan-model",
    )
    planner = ToolchainPlanner(settings)

    plan = planner.plan(case=make_case(), availability=availability())

    assert plan.planner == "heuristic"
    assert any("未安装 AgentScope" in note for note in plan.notes)


def test_planner_reuses_summary_credentials(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner.agentscope_available", lambda: True)
    captured: dict[str, object] = {}

    def backend(request: dict) -> dict:
        captured.update(request)
        return {"steps": ["qwen_judgment"], "rationale": "先做感知判断"}

    settings = Settings(
        model_mode="remote",
        agent_orchestration_enabled=True,
        external_summary_enabled=True,
        external_summary_base_url="http://summary.local/v1",
        external_summary_api_key="summary-key",
        external_summary_model="summary-model",
    )
    integrations = OptionalIntegrations(settings)
    planner = ToolchainPlanner(settings, integrations=integrations, backend=backend)

    plan = planner.plan(case=make_case(), availability=availability())

    assert plan.planner == "agentscope"
    assert plan.steps == ["qwen_judgment"]
    assert plan.rationale == "先做感知判断"
    assert captured["task"] == "plan_tool_chain"
    assert "case_context" not in captured
    assert find_external_violations(captured) == []


def test_planner_falls_back_when_backend_raises(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner.agentscope_available", lambda: True)

    def backend(request: dict) -> dict:
        raise RuntimeError("planner offline")

    settings = Settings(
        agent_orchestration_enabled=True,
        agent_planner_api_key="plan-key",
        agent_planner_model="plan-model",
    )
    planner = ToolchainPlanner(settings, backend=backend)

    plan = planner.plan(case=make_case(), availability=availability())

    assert plan.planner == "heuristic"
    assert any("planner offline" in note for note in plan.notes)


def test_analysis_service_records_plan_and_keeps_decision_slot() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "qwen.local":
            return httpx.Response(
                200,
                json={
                    "label": "cnv",
                    "confidence": 0.8,
                    "impression": "黄斑区可疑异常",
                    "findings": [{"label": "macular abnormality"}],
                },
            )
        return httpx.Response(404, json={"error": "unexpected"})

    settings = Settings(
        model_mode="remote",
        qwen_judgment_enabled=True,
        perception_service_url="http://qwen.local",
        rag_enabled=False,
        decision_enabled=False,
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    service = AnalysisService(settings, knowledge_store=None, integrations=integrations)

    result = service.analyze(make_case(), service.start())

    stages = {stage.key: stage for stage in result.stages}
    assert stages["planning"].status == "completed"
    assert "确定性兜底规划" in stages["planning"].detail
    assert result.toolchain_plan["planner"] == "heuristic"
    assert result.toolchain_plan["steps"] == ["qwen_judgment"]

    decision_component = next(
        item for item in result.component_results if item.key == "decision"
    )
    assert decision_component.status == "skipped"
    assert "训练暂缓" in decision_component.detail
    assert result.status == "completed"


def test_analysis_service_uses_agentscope_plan_when_available(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.planner.agentscope_available", lambda: True)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "qwen.local":
            return httpx.Response(
                200,
                json={"label": "cnv", "confidence": 0.7, "impression": "可疑"},
            )
        return httpx.Response(404, json={"error": "unexpected"})

    settings = Settings(
        model_mode="remote",
        qwen_judgment_enabled=True,
        perception_service_url="http://qwen.local",
        rag_enabled=True,
        agent_orchestration_enabled=True,
        agent_planner_api_key="plan-key",
        agent_planner_model="plan-model",
    )
    integrations = OptionalIntegrations(
        settings,
        client_factory=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs
        ),
    )
    planner = ToolchainPlanner(
        settings,
        integrations=integrations,
        backend=lambda request: {
            "steps": ["qwen_judgment", "external_summary"],
            "rationale": "仅执行感知与总结",
        },
    )
    service = AnalysisService(
        settings,
        knowledge_store=None,
        integrations=integrations,
        planner=planner,
    )

    result = service.analyze(make_case(), service.start())

    assert result.toolchain_plan["planner"] == "agentscope"
    assert result.toolchain_plan["steps"] == ["qwen_judgment"]
    assert result.toolchain_plan["skipped"]["external_summary"]
    assert "AgentScope 模型规划" in next(
        stage.detail for stage in result.stages if stage.key == "planning"
    )
    assert "工具链由确定性规则编排，未使用模型规划" not in result.safety_flags
