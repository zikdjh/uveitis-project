"""Declarative description of the optional judgment tool chain.

The analysis pipeline is a chain of optional skills. Some of them are
available today (Qwen judgment, RAG retrieval, web search, external
summary), while the supplementary decision model keeps its slot in the
chain even though its training is deferred and the service stays off.

The declarations below are the single source of truth shared by the
deterministic planner and the AgentScope planner, so both describe the
same chain to the rest of the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TOOLCHAIN_ORDER: tuple[str, ...] = (
    "qwen_judgment",
    "retrieval",
    "decision",
    "web_search",
    "external_summary",
)
"""Canonical execution order. Plans are always normalized to this order."""

CORE_STEPS: frozenset[str] = frozenset({"qwen_judgment"})
"""Skills that are executed whenever they are available, even if a planner
omits them."""


@dataclass(frozen=True)
class ToolchainSkill:
    """One optional skill in the judgment tool chain."""

    key: str
    label: str
    description: str
    consumes: tuple[str, ...]
    produces: str
    deferred: bool = False


SKILLS: tuple[ToolchainSkill, ...] = (
    ToolchainSkill(
        key="qwen_judgment",
        label="Qwen 微调判断",
        description="调用本地微调后的 Qwen 模型，对病例与影像给出结构化判断。",
        consumes=(),
        produces="findings/impression/confidence",
    ),
    ToolchainSkill(
        key="retrieval",
        label="RAG 证据检索",
        description="在本地知识索引中检索指南、文献与相似病例证据。",
        consumes=("qwen_judgment",),
        produces="evidence",
    ),
    ToolchainSkill(
        key="decision",
        label="补充决策（暂缓训练）",
        description=(
            "预留的补充决策模型调用位。训练暂缓期间该槽位保留但不启用，"
            "不影响主链路。"
        ),
        consumes=("qwen_judgment", "retrieval"),
        produces="differential/urgency",
        deferred=True,
    ),
    ToolchainSkill(
        key="web_search",
        label="网络搜索辅助",
        description="按管理员配置的服务商顺序执行外部检索，补充最新公开信息。",
        consumes=("qwen_judgment", "decision"),
        produces="web_evidence",
    ),
    ToolchainSkill(
        key="external_summary",
        label="外部 API 总结",
        description="把结构化判断、RAG 证据与网络证据交给外部模型整理解释。",
        consumes=("qwen_judgment", "retrieval", "web_search"),
        produces="summary/recommendations",
    ),
)

SKILL_BY_KEY: dict[str, ToolchainSkill] = {skill.key: skill for skill in SKILLS}


@dataclass(frozen=True)
class SkillAvailability:
    """Whether a skill can run right now, and the reason when it cannot."""

    available: bool
    reason: str


@dataclass
class ToolchainPlan:
    """The planned invocation set for one analysis run."""

    steps: list[str]
    skipped: dict[str, str] = field(default_factory=dict)
    planner: str = "heuristic"
    rationale: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "planner": self.planner,
            "steps": list(self.steps),
            "skipped": dict(self.skipped),
            "rationale": self.rationale,
            "notes": list(self.notes),
        }


def skill_catalog(
    availability: dict[str, SkillAvailability] | None = None,
) -> list[dict[str, Any]]:
    """Describe the chain for planner prompts and admin diagnostics."""

    availability = availability or {}
    catalog: list[dict[str, Any]] = []
    for index, skill in enumerate(SKILLS, start=1):
        state = availability.get(skill.key)
        catalog.append(
            {
                "order": index,
                "key": skill.key,
                "label": skill.label,
                "description": skill.description,
                "consumes": list(skill.consumes),
                "produces": skill.produces,
                "deferred": skill.deferred,
                "available": bool(state.available) if state else False,
                "status": state.reason if state else "未提供可用性信息",
            }
        )
    return catalog


def normalize_steps(
    raw_steps: Any,
    availability: dict[str, SkillAvailability],
    *,
    planner: str,
    rationale: str = "",
) -> ToolchainPlan:
    """Coerce a planner proposal into a safe, ordered plan.

    Rules applied here, independent of which planner produced the proposal:

    - unknown skill keys are dropped and reported;
    - unavailable skills are skipped with their configured reason;
    - available but unselected optional skills are reported as skipped;
    - core skills are restored when a planner drops them;
    - the surviving steps are sorted into the canonical chain order.
    """

    requested: list[str] = []
    if isinstance(raw_steps, str):
        raw_steps = [raw_steps]
    if isinstance(raw_steps, (list, tuple, set)):
        for item in raw_steps:
            key = str(item).strip()
            if key and key not in requested:
                requested.append(key)

    notes: list[str] = []
    skipped: dict[str, str] = {}

    unknown = [key for key in requested if key not in SKILL_BY_KEY]
    if unknown:
        notes.append("已忽略未登记的工具：" + "、".join(unknown))

    selected: list[str] = []
    for key in requested:
        if key not in SKILL_BY_KEY:
            continue
        state = availability.get(key)
        if state is None or not state.available:
            skipped[key] = (
                state.reason if state and state.reason else "当前不可用"
            )
            continue
        selected.append(key)

    for key in TOOLCHAIN_ORDER:
        if key in selected:
            continue
        state = availability.get(key)
        if not state or not state.available:
            skipped.setdefault(
                key, state.reason if state and state.reason else "当前不可用"
            )
            continue
        if key in CORE_STEPS:
            selected.append(key)
            notes.append(f"规划器未选择必需步骤 {key}，已回退执行")
        else:
            skipped.setdefault(key, "规划器本次未选择，非必需步骤")

    ordered = [key for key in TOOLCHAIN_ORDER if key in selected]
    return ToolchainPlan(
        steps=ordered,
        skipped=skipped,
        planner=planner,
        rationale=rationale.strip(),
        notes=notes,
    )
