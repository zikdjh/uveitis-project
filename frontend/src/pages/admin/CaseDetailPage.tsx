import {
  ArrowLeft,
  CheckCircle2,
  CircleSlash2,
  LoaderCircle,
  LockKeyhole,
  Network,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getCase, type CaseRecord } from "@/api/cases";

export default function AdminCaseDetailPage() {
  const { caseId = "" } = useParams();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getCase(caseId)
      .then(setItem)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "病例加载失败"),
      )
      .finally(() => setLoading(false));
  }, [caseId]);

  return (
    <section className="page case-detail-page">
      {error && <div className="notice error-notice">{error}</div>}
      {loading && !item && (
        <section className="panel">
          <div className="loading-panel"><LoaderCircle className="spin" size={22} /> 正在读取病例</div>
        </section>
      )}
      {item && (
        <>
          <div className="case-detail-header">
            <div className="case-detail-title">
              <p className="case-breadcrumb">病例审计 / 病例 {item.id.slice(0, 8)}</p>
              <div className="detail-title">
                <h1>{item.patient_age} 岁 · {sexText[item.patient_sex]}</h1>
                <span className={`status ${item.status}`}>{statusText[item.status]}</span>
              </div>
              <p className="detail-subtitle">{item.complaint}</p>
              <div className="case-detail-meta">
                <span><LockKeyhole size={13} /> 只读审计</span>
                <span>影像 {item.images.length} 张</span>
                <span>更新 {new Date(item.updated_at).toLocaleString("zh-CN")}</span>
              </div>
            </div>
            <Link className="button secondary" to="/admin/cases"><ArrowLeft size={15} /> 返回列表</Link>
          </div>
          <section className="panel case-audit-panel">
          <div className="clinical-facts">
            <div><span>患者</span><strong>{item.patient_age} 岁 · {sexText[item.patient_sex]}</strong></div>
            <div><span>患眼</span><strong>{eyeText[item.affected_eye]}</strong></div>
            <div><span>影像</span><strong>{item.images.length} 张</strong></div>
          </div>
          <div className="clinical-text"><span>主诉</span><p>{item.complaint}</p></div>
          <div className="clinical-text"><span>病史与检查</span><p>{item.medical_history || "未填写"}</p></div>
          <div className="clinical-text"><span>辅助分析</span><p>{item.analysis?.summary || item.analysis?.impression || "尚未形成可用结果"}</p></div>
          <div className="clinical-text"><span>复核</span><p>{item.review ? `${item.review.reviewer} · ${new Date(item.review.reviewed_at).toLocaleString("zh-CN")}` : "尚未完成"}</p></div>
          <div className="clinical-text"><span>医生最终印象</span><p>{item.review?.final_impression || "尚未形成"}</p></div>
          </section>
          {item.analysis && (
            <section className="panel case-toolchain-panel">
              <div className="case-toolchain-heading">
                <div>
                  <span className="case-panel-kicker"><Network size={14} /> 调用链诊断</span>
                  <h2>本次规划与执行</h2>
                  <p>{planDescription(item.analysis.toolchain_plan.planner)}</p>
                </div>
                <span className={`toolchain-planner-badge ${item.analysis.toolchain_plan.planner === "agentscope" ? "model" : "fallback"}`}>
                  {plannerText[item.analysis.toolchain_plan.planner] ?? "确定性回退"}
                </span>
              </div>

              <div className="toolchain-metrics">
                <div><span>规划步骤</span><strong>{item.analysis.toolchain_plan.steps.length}</strong></div>
                <div><span>跳过步骤</span><strong>{Object.keys(item.analysis.toolchain_plan.skipped).length}</strong></div>
                <div><span>组件耗时</span><strong>{formatLatency(item.analysis.component_results.reduce((total, component) => total + component.latency_ms, 0))}</strong></div>
              </div>

              {item.analysis.toolchain_plan.rationale && (
                <div className="toolchain-rationale">
                  <span>规划说明</span>
                  <p>{item.analysis.toolchain_plan.rationale}</p>
                </div>
              )}

              <div className="toolchain-step-list">
                {item.analysis.component_results.map((component) => (
                  <article key={component.key} className={`toolchain-step ${component.status}`}>
                    <div className="toolchain-step-icon">
                      {component.status === "completed" && <CheckCircle2 size={17} />}
                      {component.status === "skipped" && <CircleSlash2 size={17} />}
                      {component.status === "running" && <LoaderCircle className="spin" size={17} />}
                      {component.status === "failed" && <CircleSlash2 size={17} />}
                      {component.status === "pending" && <Network size={17} />}
                    </div>
                    <div className="toolchain-step-copy">
                      <div className="toolchain-step-title">
                        <strong>{component.label}</strong>
                        <span>{componentStatusText[component.status]}</span>
                      </div>
                      <p>{component.detail || componentStatusText[component.status]}</p>
                    </div>
                    {component.latency_ms > 0 && <span className="toolchain-step-latency">{component.latency_ms} ms</span>}
                  </article>
                ))}
                {item.analysis.component_results.length === 0 && (
                  <div className="toolchain-empty">本次分析没有记录可展示的链路组件。</div>
                )}
              </div>

              {item.analysis.toolchain_plan.notes.length > 0 && (
                <div className="toolchain-notes">
                  <span>规划备注</span>
                  <ul>{item.analysis.toolchain_plan.notes.map((note) => <li key={note}>{note}</li>)}</ul>
                </div>
              )}
            </section>
          )}
        </>
      )}
    </section>
  );
}

const sexText = { F: "女", M: "男", U: "未说明" };
const eyeText = { OD: "右眼", OS: "左眼", OU: "双眼", UNKNOWN: "未确认" };
const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};
const plannerText: Record<string, string> = {
  agentscope: "模型规划",
  heuristic: "确定性回退",
};
const componentStatusText = {
  pending: "等待执行",
  running: "执行中",
  completed: "已完成",
  skipped: "已跳过",
  failed: "执行失败",
};

function planDescription(planner: string) {
  return planner === "agentscope"
    ? "由 AgentScope 选择本次需要执行的增强能力，后端按规范化顺序执行。"
    : "未使用模型规划，后端按可用能力顺序确定性执行。";
}

function formatLatency(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${value} ms`;
}
