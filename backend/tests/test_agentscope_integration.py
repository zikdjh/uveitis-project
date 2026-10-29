"""Opt-in integration test for the real AgentScope dependency.

Skipped unless ``agentscope`` is installed (``uv sync --extra agent``).
The language model call is stubbed, so this exercises the AgentScope
plumbing: toolkit registration, permission wiring, the ReAct loop and the
structured-output handshake of :meth:`ToolchainPlanner._agentscope_backend`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx2
import pytest

pytest.importorskip("agentscope")

from agentscope.message import TextBlock, ToolCallBlock  # noqa: E402
from agentscope.model import ChatResponse  # noqa: E402
from agentscope.formatter import OpenAIChatFormatter  # noqa: E402

from app.agents.planner import ToolchainPlanner  # noqa: E402
from app.agents.toolchain import SkillAvailability, skill_catalog  # noqa: E402
from app.core.config import Settings  # noqa: E402


PLAN_PAYLOAD = {
    "steps": ["qwen_judgment", "retrieval"],
    "rationale": "先做感知判断，再补充本地证据。",
}


class _StubModel:
    """Minimal chat model that answers with one structured-output tool call."""

    model = "stub-planner"
    context_size = 128000

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls = 0
        self.formatter = OpenAIChatFormatter()

    async def count_tokens(self, *args: Any, **kwargs: Any) -> int:
        """Report a small, constant token count for compression checks."""

        return 1

    async def __call__(
        self,
        messages: Any,
        tools: Any = None,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> ChatResponse:
        self.calls += 1
        if self.calls == 1:
            return ChatResponse(
                content=[
                    ToolCallBlock(
                        id="call-1",
                        name="GenerateStructuredOutput",
                        input=json.dumps(self.payload, ensure_ascii=False),
                    )
                ],
                is_last=True,
            )
        return ChatResponse(
            content=[TextBlock(text="structured output delivered")],
            is_last=True,
        )


def _availability() -> dict[str, SkillAvailability]:
    return {
        "qwen_judgment": SkillAvailability(True, "已配置"),
        "retrieval": SkillAvailability(True, "已配置"),
        "decision": SkillAvailability(False, "训练暂缓，槽位保留但未启用"),
        "web_search": SkillAvailability(False, "网络搜索 API 未启用"),
        "external_summary": SkillAvailability(False, "外部总结 API 未启用"),
    }


def test_agentscope_backend_returns_structured_plan(monkeypatch) -> None:
    settings = Settings(
        agent_orchestration_enabled=True,
        agent_planner_api_key="planner-key",
        agent_planner_model="planner-model",
        agent_planner_max_steps=4,
        agent_planner_timeout_seconds=60,
    )
    planner = ToolchainPlanner(settings)
    stub = _StubModel(PLAN_PAYLOAD)
    monkeypatch.setattr(planner, "_build_model", lambda credentials: stub)

    proposal = planner._agentscope_backend(
        {
            "task": "plan_tool_chain",
            "tool_chain": skill_catalog(_availability()),
            "instructions": ["Select only available skills."],
        }
    )

    assert proposal["steps"] == PLAN_PAYLOAD["steps"]
    assert proposal["rationale"] == PLAN_PAYLOAD["rationale"]
    assert stub.calls >= 1


def test_planner_http_client_uses_httpx2_and_ignores_process_proxy() -> None:
    planner = ToolchainPlanner(Settings(external_network_trust_env=False))

    client = planner._client_kwargs()["http_client"]

    assert isinstance(client, httpx2.AsyncClient)
    assert client.trust_env is False
    asyncio.run(client.aclose())


def test_agentscope_backend_result_survives_plan_normalization(monkeypatch) -> None:
    settings = Settings(
        agent_orchestration_enabled=True,
        agent_planner_api_key="planner-key",
        agent_planner_model="planner-model",
        agent_planner_max_steps=4,
        agent_planner_timeout_seconds=60,
    )
    planner = ToolchainPlanner(settings)
    monkeypatch.setattr(
        "app.agents.planner.agentscope_available",
        lambda: True,
    )
    monkeypatch.setattr(
        planner,
        "_agentscope_backend",
        lambda request: dict(PLAN_PAYLOAD),
    )

    from datetime import UTC, datetime

    from app.schemas.case import CaseRead

    now = datetime.now(UTC)
    case = CaseRead(
        id="case-1",
        owner_id="doctor-1",
        patient_age=42,
        patient_sex="F",
        complaint="左眼视物模糊",
        medical_history="无特殊",
        affected_eye="OS",
        consent_confirmed=True,
        status="created",
        created_at=now,
        updated_at=now,
    )

    plan = planner.plan(case=case, availability=_availability())

    assert plan.planner == "agentscope"
    assert plan.steps == ["qwen_judgment", "retrieval"]
    assert plan.skipped["decision"] == "训练暂缓，槽位保留但未启用"
