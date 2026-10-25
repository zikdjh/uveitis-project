import { useEffect, useState } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";

import { getCase, type CaseRecord } from "@/api/cases";
import { CaseContext, type CaseContextValue } from "@/pages/doctor/CaseContext";

export default function CaseLayout() {
  const { caseId = "" } = useParams();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCase(caseId)
      .then(setItem)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "病例加载失败"),
      );
  }, [caseId]);

  const value: CaseContextValue | null = item ? { item, setItem } : null;

  return (
    <section className="page case-detail-page">
      {error && <div className="notice error-notice">{error}</div>}
      {item && value ? (
        <CaseContext.Provider value={value}>
          <div className="case-detail-header">
            <div>
              <p className="eyebrow">病例 {item.id.slice(0, 8)}</p>
              <div className="detail-title">
                <h1>{item.patient_age} 岁 · {sexText[item.patient_sex]}</h1>
                <span className={`status ${item.status}`}>{statusText[item.status]}</span>
              </div>
              <p className="detail-subtitle">{item.complaint}</p>
            </div>
            <NavLink className="button secondary" to="/doctor/cases">返回病例列表</NavLink>
          </div>
          <nav className="case-tabs" aria-label="病例详情导航">
            <NavLink end to={`/doctor/cases/${item.id}/summary`}>资料摘要</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/images`}>影像</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/analysis`}>辅助分析</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/review`}>医生复核</NavLink>
            <NavLink to={`/doctor/cases/${item.id}/report`}>报告</NavLink>
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
