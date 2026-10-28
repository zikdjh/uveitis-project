"""AgentScope-backed planner for the optional judgment tool chain.

The planner only decides *which* optional skills run. Execution stays in
``AnalysisService`` so that availability gating, failure handling and the
audit trail remain deterministic. When AgentScope is not installed, not
enabled, or fails, the deterministic plan is used and the run continues.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from dataclasses import dataclass
from typing import Any, Callable

from app.agents.toolchain import (
    SkillAvailability,
    ToolchainPlan,
    normalize_steps,
    skill_catalog,
)
from app.core.config import Settings
from app.schemas.case import CaseRead
from app.core.external_boundary import assert_external_payload


PlannerBackend = Callable[[dict[str, Any]], dict[str, Any]]


PLANNER_SYSTEM_PROMPT = """You plan the tool chain of an ophthalmology \
case-review assistant.

You do not diagnose. You only decide which registered skills should run for \
the current case, in the canonical order given to you.

Rules:
1. Call list_toolchain_options before deciding.
2. Only select skills whose available flag is true.
3. Never select a skill whose available flag is false, even if the case \
would clearly benefit from it.
4. Select the smallest set that is useful for this case. Extra skills cost \
latency and quota, and unavailable skills are skipped by the executor \
anyway.
5. Return the selected skill keys in the canonical order, plus one short \
sentence of rationale.
"""


def agentscope_available() -> bool:
    """Report whether the optional AgentScope dependency can be imported."""

    try:
        return importlib.util.find_spec("agentscope") is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


@dataclass(frozen=True)
class PlannerCredentials:
    """Resolved planner model credentials."""

    protocol: str
    base_url: str
    api_key: str
    model: str
    source: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.model)


class ToolchainPlanner:
    """Plans the optional judgment chain, with a deterministic fallback."""

    def __init__(
        self,
        settings: Settings,
        integrations: Any | None = None,
        backend: PlannerBackend | None = None,
    ) -> None:
        self.settings = settings
        self.integrations = integrations
        self._backend = backend

    # ------------------------------------------------------------------
    # credentials
    # ------------------------------------------------------------------
    def credentials(self) -> PlannerCredentials:
        """Resolve planner credentials.

        Dedicated ``APP_AGENT_PLANNER_*`` values win. When they are absent
        and ``agent_planner_use_summary_credentials`` is enabled, the
        administrator-managed external summary endpoint is reused so a
        deployment that already configured one external model does not need
        a second configuration entry.
        """

        if self.settings.agent_planner_api_key and self.settings.agent_planner_model:
            return PlannerCredentials(
                protocol=self.settings.agent_planner_protocol,
                base_url=self.settings.agent_planner_base_url,
                api_key=self.settings.agent_planner_api_key,
                model=self.settings.agent_planner_model,
                source="agent_planner_settings",
            )

        if (
            self.settings.agent_planner_use_summary_credentials
            and self.integrations is not None
        ):
            snapshot = self.integrations.external_summary_credentials()
            if snapshot.get("api_key") and snapshot.get("model"):
                return PlannerCredentials(
                    protocol=str(
                        snapshot.get("protocol") or "openai_chat_completions"
                    ),
                    base_url=str(snapshot.get("base_url") or ""),
                    api_key=str(snapshot.get("api_key") or ""),
                    model=str(snapshot.get("model") or ""),
                    source="external_summary_settings",
                )

        return PlannerCredentials(
            protocol=self.settings.agent_planner_protocol,
            base_url=self.settings.agent_planner_base_url,
            api_key="",
            model=self.settings.agent_planner_model,
            source="unconfigured",
        )

    # ------------------------------------------------------------------
    # planning entry point
    # ------------------------------------------------------------------
    def plan(
        self,
        *,
        case: CaseRead,
        availability: dict[str, SkillAvailability],
    ) -> ToolchainPlan:
        """Plan the optional chain for one case.

        ``case`` is accepted for call-site symmetry only. It is never part of
        the planner request: planning works from the skill catalog and the
        computed availability, so no case field reaches the planner model.
        """

        del case
        notes: list[str] = []

        if not self.settings.agent_orchestration_enabled:
            return self._fallback(
                availability,
                notes + ["AgentScope 工具链规划未启用，使用确定性顺序"],
            )

        if not agentscope_available():
            return self._fallback(
                availability,
                notes + ["未安装 AgentScope，使用确定性顺序"],
            )

        credentials = self.credentials()
        if not credentials.configured:
            return self._fallback(
                availability,
                notes + ["规划模型凭据未配置，使用确定性顺序"],
            )

        backend = self._backend or self._agentscope_backend
        try:
            request = assert_external_payload(
                self._build_request(availability),
                service="工具链规划",
            )
            proposal = backend(request)
            if not isinstance(proposal, dict):
                raise ValueError("规划器未返回 JSON 对象")
            plan = normalize_steps(
                proposal.get("steps"),
                availability,
                planner="agentscope",
                rationale=str(proposal.get("rationale") or ""),
            )
            plan.notes.extend(notes)
            return plan
        except Exception as exc:  # noqa: BLE001 - never block the case
            return self._fallback(
                availability,
                notes
                + [
                    "AgentScope 规划失败，已回退确定性顺序："
                    f"{type(exc).__name__}: {exc}"
                ],
            )

    def _fallback(
        self,
        availability: dict[str, SkillAvailability],
        notes: list[str],
    ) -> ToolchainPlan:
        plan = normalize_steps(
            [key for key, state in availability.items() if state.available],
            availability,
            planner="heuristic",
            rationale="按可用性顺序执行全部已配置工具，未启用模型规划。",
        )
        plan.notes = notes + plan.notes
        return plan

    def _build_request(
        self,
        availability: dict[str, SkillAvailability],
    ) -> dict[str, Any]:
        """Build the planner request.

        The planner is an external model call, so the request carries the
        skill catalog and selection rules only. Case fields and images are
        never included, not even as a boolean hint about image presence.
        """

        request: dict[str, Any] = {
            "task": "plan_tool_chain",
            "tool_chain": skill_catalog(availability),
            "instructions": [
                "Select only skills whose available flag is true.",
                "Return the selected keys in canonical order.",
                "Plan from the catalog and availability only.",
                "Do not diagnose, and do not ask for case or patient data.",
            ],
        }
        return request

    # ------------------------------------------------------------------
    # AgentScope backend
    # ------------------------------------------------------------------
    def _build_model(self, credentials: PlannerCredentials) -> Any:
        """Build the AgentScope chat model for the configured protocol."""

        from agentscope.credential import AnthropicCredential, OpenAICredential
        from agentscope.model import (
            AnthropicChatModel,
            OpenAIChatModel,
            OpenAIResponseModel,
        )

        protocol = credentials.protocol
        common = {
            "model": credentials.model,
            "stream": False,
            "max_retries": self.settings.agent_planner_max_retries,
        }
        if protocol == "anthropic_messages":
            return AnthropicChatModel(
                credential=AnthropicCredential(
                    api_key=credentials.api_key,
                    base_url=credentials.base_url or None,
                ),
                **common,
            )
        if protocol == "openai_responses":
            return OpenAIResponseModel(
                credential=OpenAICredential(
                    api_key=credentials.api_key,
                    base_url=credentials.base_url or None,
                ),
                **common,
            )
        return OpenAIChatModel(
            credential=OpenAICredential(
                api_key=credentials.api_key,
                base_url=credentials.base_url or None,
            ),
            **common,
        )

    def _agentscope_backend(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run one AgentScope planning conversation.

        The agent gets the chain description as a read-only tool and must
        answer with a structured plan. This is the only AgentScope entry
        point; the returned plan is validated before the executor runs it.
        """

        from agentscope.agent import Agent, InjectionConfig, ReActConfig
        from agentscope.message import UserMsg
        from agentscope.permission import PermissionBehavior, PermissionDecision
        from agentscope.tool import FunctionTool, Toolkit
        from pydantic import BaseModel, Field

        credentials = self.credentials()
        model = self._build_model(credentials)
        chain = list(request.get("tool_chain") or [])

        def list_toolchain_options() -> list[dict[str, Any]]:
            """Return the registered tool-chain skills with availability."""

            return chain

        toolkit = Toolkit(
            tools=[
                FunctionTool(
                    list_toolchain_options,
                    name="list_toolchain_options",
                    description=(
                        "Return every registered tool-chain skill with its "
                        "key, canonical order, description and availability."
                    ),
                    is_read_only=True,
                    permission=PermissionDecision(
                        behavior=PermissionBehavior.ALLOW,
                        message="只读的工具链清单查询，总是允许。",
                    ),
                )
            ]
        )

        class PlanSchema(BaseModel):
            """Structured tool-chain plan returned by the planning agent."""

            steps: list[str] = Field(
                description="Selected skill keys in canonical order."
            )
            rationale: str = Field(
                default="", description="One short sentence of rationale."
            )

        agent = Agent(
            name="toolchain-planner",
            system_prompt=PLANNER_SYSTEM_PROMPT,
            model=model,
            toolkit=toolkit,
            react_config=ReActConfig(
                max_iters=max(2, self.settings.agent_planner_max_steps)
            ),
            injection_config=InjectionConfig(inject_runtime_state=False),
        )

        async def _run() -> dict[str, Any]:
            message = UserMsg(
                name="case-review-service",
                content=json.dumps(request, ensure_ascii=False),
            )
            reply = await agent.reply(message, structured_schema=PlanSchema)
            return dict(reply.structured_output or {})

        return _run_coroutine(
            _run(),
            timeout=self.settings.agent_planner_timeout_seconds,
        )


def _run_coroutine(coroutine: Any, *, timeout: float) -> dict[str, Any]:
    """Run an AgentScope coroutine from the synchronous analysis path."""

    async def _with_timeout() -> dict[str, Any]:
        return await asyncio.wait_for(coroutine, timeout=timeout)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_with_timeout())
    raise RuntimeError("规划器不能运行在已激活的事件循环中")
