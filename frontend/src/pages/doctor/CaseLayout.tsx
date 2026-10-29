import { ArrowLeft, ClipboardList, FileText, Images, ScanSearch, Stethoscope } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";

import {
  getAnalysisJob,
  getCase,
  type AnalysisJobRecord,
  type CaseRecord,
} from "@/api/cases";
import { CaseContext, type CaseContextValue } from "@/pages/doctor/CaseContext";

const analysisPollDelays = [700, 1000, 1500, 2000, 2500, 3000];
const analysisPollTimeoutMs = 15 * 60 * 1000;

export default function CaseLayout() {
  const { caseId = "" } = useParams();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [analysisJob, setAnalysisJob] = useState<AnalysisJobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setItem(null);
    setAnalysisJob(null);
    setError(null);
    Promise.all([getCase(caseId), getAnalysisJob(caseId)])
      .then(([nextCase, nextJob]) => {
        if (cancelled) return;
        setItem(nextCase);
        setAnalysisJob(nextJob);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setError(reason instanceof Error ? reason.message : "病例加载失败");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  useEffect(() => {
    if (item?.status !== "analyzing") return;
    let cancelled = false;
    let timeoutId: number | undefined;
    let attempt = 0;
    const startedAt = Date.now();

    const poll = async () => {
      if (cancelled || document.visibilityState === "hidden") return;
      try {
        const [nextCase, nextJob] = await Promise.all([
          getCase(caseId),
          getAnalysisJob(caseId),
        ]);
        if (cancelled) return;
        setItem(nextCase);
        setAnalysisJob(nextJob);
        setError(null);
        if (nextCase.status !== "analyzing") return;
      } catch (reason) {
        if (cancelled) return;
        setError(
          reason instanceof Error
            ? `分析进度更新失败：${reason.message}`
            : "分析进度更新失败，正在重试",
        );
      }
      if (Date.now() - startedAt >= analysisPollTimeoutMs) {
        setError("分析任务仍在处理中，可稍后刷新页面继续查看。");
        return;
      }
      const delay = analysisPollDelays[
        Math.min(attempt, analysisPollDelays.length - 1)
      ];
      attempt += 1;
      timeoutId = window.setTimeout(() => void poll(), delay);
    };

    const handleVisibility = () => {
      if (document.visibilityState === "hidden" || cancelled) return;
      window.clearTimeout(timeoutId);
      attempt = 0;
      void poll();
    };

    document.addEventListener("visibilitychange", handleVisibility);
    timeoutId = window.setTimeout(() => void poll(), analysisPollDelays[0]);
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [caseId, item?.status]);

  const value: CaseContextValue | null = item
    ? { item, setItem, analysisJob, setAnalysisJob }
    : null;

  return (
    <section className="page case-detail-page">
      {error && <div className="notice error-notice">{error}</div>}
      {item && value ? (
        <CaseContext.Provider value={value}>
          <div className="case-detail-header">
            <div className="case-detail-title">
              <p className="case-breadcrumb">病例管理 / 病例 {item.id.slice(0, 8)}</p>
              <div className="detail-title">
                <h1>{item.patient_age} 岁 · {sexText[item.patient_sex]}</h1>
                <span className={`status ${item.status}`}>{statusText[item.status]}</span>
              </div>
              <p className="detail-subtitle">{item.complaint}</p>
              <div className="case-detail-meta">
                <span>影像 {item.images.length} 张</span>
                <span>更新 {new Date(item.updated_at).toLocaleString("zh-CN")}</span>
              </div>
            </div>
            <NavLink className="button secondary" to="/doctor/cases"><ArrowLeft size={15} /> 返回病例列表</NavLink>
          </div>
          <nav className="case-tabs" aria-label="病例详情导航">
            <NavLink end to={`/doctor/cases/${item.id}/summary`}><ClipboardList size={15} /> 资料摘要</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/images`}><Images size={15} /> 影像</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/analysis`}><ScanSearch size={15} /> 辅助分析</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/review`}><Stethoscope size={15} /> 医生复核</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/report`}><FileText size={15} /> 报告</NavLink>
          </nav>
          <Outlet />
        </CaseContext.Provider>
      ) : !error ? <div className="route-loading">正在加载病例</div> : null}
    </section>
  );
}

const sexText = { F: "女", M: "男", U: "未说明" };
const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};
