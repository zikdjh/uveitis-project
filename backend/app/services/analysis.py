from datetime import UTC, datetime

from app.core.config import Settings
from app.schemas.case import AnalysisResult, CaseRead, ModelService, PipelineStage


class AnalysisService:
    """Coordinates perception and retrieval, with decision as an optional branch."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def model_services(self) -> list[ModelService]:
        mode_status = "mock" if self.settings.model_mode == "mock" else "configured"
        decision_status = (
            mode_status if self.settings.decision_enabled else "offline"
        )
        return [
            ModelService(
                role="多模态理解",
                name=self.settings.perception_model,
                status=mode_status,
                endpoint=self.settings.perception_service_url,
            ),
            ModelService(
                role="向量检索",
                name=self.settings.retrieval_model,
                status=mode_status,
                endpoint=self.settings.retrieval_service_url,
            ),
            ModelService(
                role="补充决策（可选）",
                name=self.settings.decision_model,
                status=decision_status,
                required=False,
                enabled=self.settings.decision_enabled,
                endpoint=self.settings.decision_service_url,
            ),
            ModelService(
                role="决策备选",
                name=self.settings.fallback_model,
                status="offline",
                required=False,
                enabled=False,
            ),
        ]

    def start(self) -> AnalysisResult:
        stages = [
            PipelineStage(key="intake", label="病例结构化", status="completed"),
            PipelineStage(key="preprocess", label="影像预处理", status="pending"),
            PipelineStage(key="perception", label="多模态理解", status="pending"),
            PipelineStage(key="retrieval", label="证据检索", status="pending"),
            PipelineStage(
                key="decision",
                label="补充决策",
                status="pending" if self.settings.decision_enabled else "skipped",
                detail=(
                    "可选补充方案，按项目进度启用"
                    if not self.settings.decision_enabled
                    else "决策模型补充已启用，等待推理服务"
                ),
            ),
            PipelineStage(key="safety", label="安全校验", status="pending"),
            PipelineStage(key="report", label="报告整理", status="pending"),
        ]
        return AnalysisResult(
            status="queued",
            model_mode=self.settings.model_mode,
            stages=stages,
            started_at=datetime.now(UTC),
        )

    def analyze(self, case: CaseRead, queued: AnalysisResult) -> AnalysisResult:
        stages = [
            PipelineStage(key="intake", label="病例结构化", status="completed"),
            PipelineStage(
                key="preprocess",
                label="影像预处理",
                status="completed" if case.images else "skipped",
                detail=f"已接收 {len(case.images)} 张影像" if case.images else "无影像，仅走文本路径",
            ),
            PipelineStage(
                key="perception",
                label="多模态理解",
                status="skipped",
                detail="演示模式未调用模型",
            ),
            PipelineStage(
                key="retrieval",
                label="证据检索",
                status="skipped",
                detail="BGE-M3 生成向量，zvec 提供本地向量索引",
            ),
            PipelineStage(
                key="decision",
                label="补充决策",
                status="skipped",
                detail=(
                    "决策模型为可选补充方案；当前流程直接进入安全校验和医生复核"
                    if not self.settings.decision_enabled
                    else "等待决策模型健康检查和评测门禁"
                ),
            ),
            PipelineStage(
                key="safety",
                label="安全校验",
                status="completed",
                detail="已保留医生复核与证据校验节点",
            ),
            PipelineStage(
                key="report",
                label="报告整理",
                status="completed",
                detail="已生成任务记录",
            ),
        ]
        return AnalysisResult(
            status="completed",
            model_mode=queued.model_mode,
            stages=stages,
            impression="本次分析未形成可复核的临床结论，请结合检查资料进行判断。",
            urgency="unknown",
            recommendations=["完善当前检查资料后可重新分析", "由医生结合原始资料进行复核"],
            safety_flags=["演示模式", "无模型证据", "必须人工复核"],
            started_at=queued.started_at,
            completed_at=datetime.now(UTC),
        )
